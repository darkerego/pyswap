#!/usr/bin/env python3.10
import json
import os
from uniswap import Uniswap
import web3
import argparse
import dotenv
from web3.exceptions import ContractLogicError
from web3.middleware import geth_poa_middleware

import lib.abi_lib
from lib import style

dotenv.load_dotenv()


class Swapper:
    def __init__(self, _private_key_: str,
                 _address_: str,
                 version: int = 2,
                 provider: str = None,
                 network: str = 'ethereum',
                 backend: str = 'uniswap'):
        if not provider:
            self.provider = self.setup_provider(network)
        else:
            self.provider = provider
        self.w3 = web3.Web3(web3.HTTPProvider(self.provider))
        self.network = network
        self.uniswap = self.setup_dex_backend(backend=backend, _version=version, provider=self.provider,
                                              _private_key=_private_key_, _address=_address_, _network=network)
        self.setup_w3_post()
        self.address = self.w3.toChecksumAddress(_address_)
        self.version = version
        self.known = None
        self.eth_balance = 0.0
        self._print = style.PrettyText()
        self.load_known_contracts()

    def setup_provider(self, network):
        provider = os.environ.get(f'{network}_http_endpoint')
        return provider

    def setup_w3_post(self):
        if self.network == 'ethereum':
            return
        else:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        s.good(f'Web3 connected to chain: {self.w3.eth.chain_id}')

    def native_currency(self):
        natives = {"ethereum": "eth", "polygon": "matic"}
        return natives.get(self.network)

    def load_known_contracts(self):
        with open(f'data/tokens_{self.network}.json', 'r') as f:
            self.known = json.load(fp=f)
        self.known = self.known.get('known_contracts')
        # s.normal(f'Loaded {len(self.known)} known contract addresses .. ')

    def setup_dex_backend(self, backend: str, _version: int, provider:str, _network:str, _private_key:str, _address:str):
        factory_contract_addr = None
        router_contract_addr = None

        with open('data/dex_contracts.json', 'r') as f:
            dexes = json.load(f)
            for dex in dexes.get('dex_map'):
                for k, v in dex.items():
                    if k == backend:
                        versions = v.get('versions')
                        for version in versions:
                            for k, v in version.items():
                                if str(_version) == k:
                                    for kk in v:
                                        for kkk, vvv in kk.items():
                                            if kkk == 'networks':
                                                for n in vvv:
                                                    if n == _network:
                                                        factory_contract_addr = kk.get('factory')
                                                        router_contract_addr = kk.get('router')
        if router_contract_addr and factory_contract_addr:
            return Uniswap(address=_address, private_key=_private_key, version=_version, provider=provider,
                           factory_contract_addr=web3.Web3.toChecksumAddress(factory_contract_addr),
                           router_contract_addr=web3.Web3.toChecksumAddress(router_contract_addr))
        return None

    def balance(self, input_token, address=None):
        if not address:
            address = self.address
        if self.known.get(self.native_currency()) == input_token:
            balance = self.w3.eth.get_balance(self.w3.toChecksumAddress(address))
        else:
            contract = self.w3.eth.contract(input_token, abi=lib.abi_lib.EIP20_ABI)
            balance = contract.functions.balanceOf(self.w3.toChecksumAddress(address)).call()
        return balance

    def verify(self, input_token, output_token):
        if not input_token:
            self._print.error('Must specify input token!')
            return False
        else:
            if self.known.get(input_token):
                input_token = self.w3.toChecksumAddress(self.known.get(input_token))

            if not output_token:
                self._print.error('Must specify output token!')
                return False
            else:
                if self.known.get(output_token):
                    output_token = self.w3.toChecksumAddress(self.known.get(output_token))
                else:
                    output_token = output_token
                try:
                    output_contract = self.w3.eth.contract(output_token, abi=lib.abi_lib.EIP20_ABI)
                except web3.exceptions.NameNotFound:
                    self._print.error(f'Invalid Contract Address: {output_token}')
                    return False
                else:
                    if self.known.get(self.native_currency()) == output_token:
                        out_symbol = self.native_currency()
                        out_decimals = 18
                    else:
                        out_symbol = output_contract.functions.symbol().call()
                        out_decimals = output_contract.functions.decimals().call()

                try:
                    input_contract = self.w3.eth.contract(input_token, abi=lib.abi_lib.EIP20_ABI)
                except web3.exceptions.NameNotFound:
                    self._print.error(f'Invalid Contract Address: {input_token}')
                    return False
                else:
                    if self.known.get(self.native_currency()) == input_token:
                        symbol = self.native_currency()
                        decimals = 18
                    else:
                        symbol = input_contract.functions.symbol().call()
                        decimals = input_contract.functions.decimals().call()
                    return symbol, decimals, input_token, output_token, out_symbol, out_decimals

    def quote_v3(self, input_token, output_token, out_decimals, raw_qty=0, fee=3000):
        try:
            raw_amount = self.uniswap.get_price_input(input_token, output_token, raw_qty, fee=fee)
        except ContractLogicError as err:
            print(type(err))
            self._print.error(f'Error: execution reverted with: {err}')
            return False
        else:
            amount = raw_amount / 10 ** out_decimals
            self._print.normal(f'Amount: {amount}, Raw: {raw_amount}')

            return amount

    def quote_v2(self, input_token, output_token, out_decimals, raw_qty):
        try:
            raw_amount = self.uniswap.get_price_input(input_token, output_token, raw_qty)
        except web3.exceptions.ContractLogicError as err:
            self._print.error(f'Error: execution reverted with: {err}')
            return False
        else:
            amount = raw_amount / 10 ** out_decimals
            self._print.normal(f'Amount: {amount}, Raw: {raw_amount}')

            return amount

    def quote(self, input_token, output_token, qty_=0, symbol=None, decimals=0, out_symbol=None, out_decimals=0):

        self._print.normal(f'Input token is: {symbol} @ {input_token} with decimals: {decimals}')
        self._print.normal(f'Output token is {out_symbol} @ {output_token} with decimals: {out_decimals}')
        if qty_ == 0:
            bal = self.balance(self.w3.toChecksumAddress(input_token))
            qty_ = bal
            self._print.normal(f'No quantity give, so swap entire raw balance of: {bal}')
        self._print.debug(f'Quote Qty is: {qty_}')
        if self.version == 3:
            return self.quote_v3(input_token=input_token, output_token=output_token, out_decimals=out_decimals, raw_qty=qty_)
        elif self.version == 2:
            return self.quote_v2(input_token=input_token, output_token=output_token, out_decimals=out_decimals, raw_qty=qty_)

    def swap(self, input_token: str, output_token: str, _qty: (float, int) = 0, raw_qty: int = 0, recipient: str = None,
             no_prompt: bool = False):
        self.eth_balance = self.w3.eth.get_balance(self.address)
        self._print.normal(f'Native {self.native_currency()} balance of this account: {self.eth_balance}')
        symbol, decimals, input_token, output_token, out_symbol, out_decimals = self.verify(input_token, output_token)
        # print(symbol, decimals, input_token, output_token, out_symbol, out_decimals)

        if raw_qty > 0:
            _qty = raw_qty
        if _qty > 0:
            _qty = int(_qty) * 10 ** decimals
        if _qty == 0.0:
            bal = self.balance(input_token)
            _qty = bal
            self._print.normal(f'Qty is Full Balance: {bal / 10 **decimals}')
        else:
            self._print.normal(f'Qty is : {_qty}')
        quote = self.quote(input_token, output_token, qty_=_qty, symbol=symbol, decimals=decimals, out_symbol=out_symbol, out_decimals=out_decimals)
        if not quote:
            return False
        self._print.normal(f'Quote is {quote}')
        if not no_prompt:

            prompt = input('>> Accept? y/n: ')
            if prompt == 'y':
                return self.uniswap.make_trade(input_token, output_token, _qty, recipient=recipient)
            else:
                self._print.warning('Canceled by user.')
                return 2
        else:
            self._print.warning('Prompt confirm quote disabled, firing away  .. ')
            return self.uniswap.make_trade(input_token, output_token, _qty, recipient=recipient)


if __name__ == '__main__':
    s = style.PrettyText()
    args = argparse.ArgumentParser(usage='pySwap Usage. See docs for details.')
    args.add_argument('-i', '--input', dest='input_token', type=str, help='Contract address or known token symbol.')
    args.add_argument('-o', '--output', dest='output_token', type=str, help='Contract address or known token symbol.')
    args.add_argument('-q', '--quantity', dest='quantity', type=float, default=0.0, help='Float quantity.')
    args.add_argument('-R', '--raw_quantity', dest='raw_quantity', type=int, default=0, help='Raw quantity.')
    args.add_argument('-r', '--recipient', dest='recipient_address', type=str, help='Optional destination address.')
    args.add_argument('-n', '--no_prompt', dest='no_prompt', action='store_true', help='Do not prompt to confirm quote.')
    args.add_argument('-N', '--network', dest='network_name', default='ethereum', choices=['ethereum', 'polygon'],
                      help='The network to connect to.')
    args.add_argument('-uv', '--uniswap_version', type=int, default=2, choices=[2, 3], help='Uniswap version.')
    args.add_argument('-w', '--wallet', dest='wallet_file', type=str, default=None,
                      help='Location of json wallet file.')
    args.add_argument('-k', '--private_key', dest='private_key', default=None, help='Specify a private key directly')
    args.add_argument('-b', '--backend', type=str, choices=['sushiswap', 'uniswap', 'kyberswap'], default='uniswap',
                      help='Dex to connect to.')
    qty = 0
    private_key = None
    address = None
    args = args.parse_args()
    if args.quantity and args.raw_quantity:
        s.error('Specify either a floating point quantity or a raw integer quanity, not both.')
        exit(1)

    if not args.wallet_file:
        wallet_file = os.environ.get('default_wallet_location')
    else:
        wallet_file = args.wallet_file
    if args.private_key and args.wallet_file:
        s.error('Specify either a json wallet file or a private key')
        exit(1)

    if not args.private_key and wallet_file:
        with open(wallet_file, 'r') as f:
            wallet = json.load(f)
            private_key = wallet.get('wallet').get('private_key')
            address = wallet.get('wallet').get('address')
        s.good(f'Read key from wallet file for account: {address}')
    if args.private_key:
        private_key = args.private_key
        address = web3.Web3.eth.account.from_key(private_key).address
        s.good(f'Private key specified from CLI for account {address} ')
    if not private_key or not address:
        print('Either specify the location of your json wallet file or a private key string. See docs.')
        exit(1)
    s.normal(f'Selected Uniswap version: {args.uniswap_version}')
    s.normal(f'Network is: {args.network_name}')
    s.normal(
        f'Params: IN: {args.input_token}, OUT: {args.output_token}, QTY: {args.quantity}, RAW: {args.raw_quantity}')
    uni = Swapper(private_key, address, version=int(args.uniswap_version), network=args.network_name, backend=args.backend)
    if uni.uniswap is None:
        print('Uniswap not configured succesfully , exiting')
        exit(1)
    txid = uni.swap(args.input_token, args.output_token, args.quantity, args.raw_quantity, args.recipient_address,
                    args.no_prompt)
    if txid == 2:
        exit(0)
    else:
        if txid:
            txhex = web3.Web3.to_hex(txid)
            s.good(f'TXID: {txhex}')
        else:
            s.error('Some Error Occurred.')
