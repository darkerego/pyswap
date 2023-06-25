#!/usr/bin/env python3.10
import argparse
import json
import os
import pprint
import sys
import time

import dotenv
import web3
from eth_account.signers.local import LocalAccount
from eth_typing.evm import ChecksumAddress
from uniswap import Uniswap
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.middleware import geth_poa_middleware
from lib.pyswap_exceptions import *
import lib.abi_lib
from lib import style
from lib.utils import json_file_load, is_valid_evm_address


try:
    from eth_utils.address import toCheckSumAddress as to_checksum_address
except ImportError:
    from eth_utils.address import to_checksum_address

try:
    from eth_utils.curried import toHex as to_hex
except ImportError:
    from eth_utils.curried import to_hex


dotenv.load_dotenv(verbose=True)


class Swapper:
    def __init__(self, _private_key_: str,
                 _address_: str,
                 version: int = 2,
                 provider: str = None,
                 network: str = 'ethereum',
                 backend: str = 'uniswap',
                 debug: bool = False):
        self.provider: str
        self.debug_mode: bool = debug
        if not provider:
            self.setup_provider(network)
        else:
            self.provider = provider
        self.w3 = web3.Web3(web3.HTTPProvider(self.provider))
        self.network = network
        self.uniswap = self.setup_dex_backend(backend=backend, _version=version, provider=self.provider,
                                              _private_key=_private_key_, _address=_address_, _network=network)
        self.account: LocalAccount = web3.Account.from_key(_private_key_)
        self.setup_w3_post()

        self.native_map = None
        self.version = version
        self.known = None
        self.eth_balance = 0.0
        self._print = style.PrettyText()
        self.load_known_contracts()

    def setup_provider(self, network: str) -> str:
        """
        Get the web3 rpc endpoint for this network
        :param network: the name of the chain (ie ethereum)
        :return: str(the provider endpoint url)
        """
        self.provider = os.environ.get(f'{network}_ws_endpoint')
        if self.provider is None:
            self.provider = os.environ.get(f'{network}_http_endpoint')
        if not self.provider:
            raise ConfigurationError("Please configure %s in your .env" % f'{network}_ws_endpoint')

        return self.provider

    def setup_w3_post(self) -> None:
        """
        Load any required middleware for this chain.
        :return: None
        """
        if self.network == 'ethereum':
            return
        else:
            if self.w3.eth.chain_id in [56, 137]:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        s.good(f'Web3 connected to chain: {self.w3.eth.chain_id}')

    @property
    def native_assets(self):
        """
        Property getter, return the native currency for this network.
        """
        if self.native_map is None:
            self.native_map = json_file_load(f'data/native_currency.json').get('native_assets')
            # print(self.native_map)
        return self.native_map.get(self.network)

    def load_known_contracts(self) -> None:
        """
        Load known contract symbol aliases to address mappings from
        data/tokens_$network.json
        :return:
        """
        known = json_file_load(f'data/tokens_{self.network}.json')
        self.known = known.get('known_contracts')

    def add_known_contract(self, contract_address: str, symbol: str) -> (False, None):
        """
        Add a contract address to symbol mapping to the local db
        :return: None
        """

        if not to_checksum_address(contract_address):
            return False
        current_known = json_file_load(f'data/tokens_{self.network}.json')
        current_known['known_contracts'][symbol] = contract_address
        with open(f'data/tokens_{self.network}.json', 'w') as ff:
            json.dump(current_known, fp=ff)

    def setup_dex_backend(self, backend: str,
                          _version: int,
                          provider: str,
                          _network: str,
                          _private_key: str,
                          _address: str) -> (Uniswap, bool):
        """
        Configure the Uniswap object class with the user supplied parameters.
        :param backend: the dex to use
        :param _version: uniswap version
        :param provider: endpoint for web3
        :param _network: the chain to connect to
        :param _private_key: users wallet key
        :param _address: users wallet address
        :return: Uniswap, None
        """
        factory_contract_addr = None
        router_contract_addr = None

        with open('data/dex_contracts.json', 'r') as dex_f:
            dexes = json.load(dex_f)
            for dex in dexes.get('dex_map'):
                for k, v in dex.items():
                    if k == backend:
                        versions = v.get('versions')
                        for version in versions:
                            for _k, _v in version.items():
                                if str(_version) == _k:
                                    for kk in _v:
                                        for kkk, vvv in kk.items():
                                            if kkk == 'networks':
                                                for n in vvv:
                                                    if n == _network:
                                                        factory_contract_addr = kk.get('factory')
                                                        router_contract_addr = kk.get('router')
        if router_contract_addr and factory_contract_addr:
            return Uniswap(address=_address, private_key=_private_key, version=_version, provider=provider,
                           factory_contract_addr=to_checksum_address(factory_contract_addr),
                           router_contract_addr=to_checksum_address(router_contract_addr),
                           web3=self.w3)
        return None

    def poll_tx_for_receipt(self, tx_hash: hex) -> (dict, bool):
        """
        Given a txid hash, query chain until tx confirms and return True.
        If not confirmed in 100 seconds, something is wrong, return False.
        :param tx_hash: hex txid
        :return: bool
        """
        poll = 0
        while True:
            if poll > 100:
                break
            poll += 1
            self._print.normal(f'Polling for receipt: {poll}/100 ... ')
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                time.sleep(1)
            else:
                receipt = receipt.__dict__
                pprint.pprint(receipt)
                return receipt
        return False

    def balance(self, input_token: (str, ChecksumAddress), _address: (str, ChecksumAddress, None) = None) -> float:
        """
        Get the web3 balance for this account, if no contract address
        is specified get the ethereum balance.
        :param input_token: contract address
        :param _address: account to check
        :return: the balance
        """
        if self.debug_mode:
            self._print.debug('Function `balance` called with args `%s %s` ' % (input_token, _address))
        if not _address:
            _address = self.account.address
        if self.known.get(self.native_assets) == input_token:
            balance = self.w3.eth.get_balance(to_checksum_address(_address))
        else:
            contract = self.w3.eth.contract(to_checksum_address(input_token), abi=lib.abi_lib.EIP20_ABI)
            balance = contract.functions.balanceOf(to_checksum_address(_address)).call()
        return balance

    def parse_contract(self, contract_address: (str, ChecksumAddress)) -> (str, int):
        local = False
        token_address = None
        for k, v in self.known.items():
            if k == contract_address:
                token_address = to_checksum_address(v)
                local = True
            else:
                if v == contract_address:
                    local = True
        if not token_address:
            token_address = to_checksum_address(contract_address)
        try:
            this_contract = self.w3.eth.contract(token_address, abi=lib.abi_lib.EIP20_ABI)
        except web3.exceptions.NameNotFound:
            self._print.error(f'Invalid Contract Address: {contract_address} or symbol alias is not known locally. '
                              f'See docs for more info.')
            return False
        else:
            if self.known.get(self.native_assets) == token_address:
                _symbol = self.native_assets
                _decimals = 18
            else:
                _symbol = this_contract.functions.symbol().call()
                _decimals = this_contract.functions.decimals().call()
                if not local:
                    self._print.normal('Adding contract address to local db ... ')
                    self.add_known_contract(ChecksumAddress(token_address), _symbol)
        return _symbol, _decimals

    def verify(self, input_token: (str, ChecksumAddress), output_token: (str, ChecksumAddress)) -> (tuple, bool):
        """
        Verify that the given contract addresses are valid contract addresses of evm tokens and
        return those tokens metadata.

        :return:  str(input_symbol), int(input_decimals), str(input_token), str(output_token), str(out_symbol),
        int(out_decimals)
        """
        if not input_token:
            self._print.error('Must specify input token!')
            return False
        else:
            if self.known.get(input_token):
                input_token = to_checksum_address(self.known.get(input_token))

            if not output_token:
                self._print.error('Must specify output token!')
                return False
            else:
                if self.known.get(output_token):
                    output_token = to_checksum_address(self.known.get(output_token))
                out_symbol, out_decimals = self.parse_contract(output_token)
                input_symbol, input_decimals = self.parse_contract(input_token)

                return input_symbol, input_decimals, input_token, output_token, out_symbol, out_decimals

    def quote_v3(self, input_token: (str, ChecksumAddress), output_token: (str, ChecksumAddress),
                 out_decimals: int, raw_qty: int = 0, fee: int = 3000) -> (float, bool):
        """
        Quote function for Uniswap v3. See documentation of Swapper.quote()
        :param raw_qty:
        :param out_decimals:
        :param output_token:
        :param input_token:
        :param fee: Optional liquidity pool fee. Uniswap will usually correctly assume this for us.
        :return: (float, bool)
        """
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

    def quote_v2(self, input_token: (str, ChecksumAddress), output_token: (str, ChecksumAddress),
                 out_decimals: int, raw_qty: int) -> (float, bool):
        """
        Quote function for uniswap v2. See function doc of Swapper.quote()

        :return: (float, bool)
        """
        try:
            raw_amount = self.uniswap.get_price_input(input_token, output_token, raw_qty)
        except web3.exceptions.ContractLogicError as err:
            self._print.error(f'Error: execution reverted with: {err}')
            return False
        else:
            amount = raw_amount / 10 ** out_decimals
            self._print.normal(f'Amount: {amount}, Raw: {raw_amount}')

            return amount

    def quote(self, input_token: (str, ChecksumAddress), output_token: (str, ChecksumAddress), qty_: int = 0,
              symbol: str = None, decimals: int = 0, out_symbol: str = None, out_decimals: int = 0):
        """
        Wrapper function that retrieves a quote from the dex backend. If no quantity is given then we check the users
        balance and use that as the qty. Function just passes parameters to the appropriate uniswap version quote
        function. See documentation of Swapper.swap()

        :return: (int, bool) the quote as a floating point
        """
        if self.debug_mode:
            self._print.debug('Function `quote` called with arguments: `%s %s %s %s %s %s %s`' % (input_token, output_token, qty_, symbol, decimals, output_token, out_decimals))
        self._print.normal(f'Input token is: {symbol} @ {input_token} with decimals: {decimals}')
        self._print.normal(f'Output token is {out_symbol} @ {output_token} with decimals: {out_decimals}')
        try:
            input_token = to_checksum_address(input_token)
        except ValueError:
            pass

        try:
            output_token = to_checksum_address(output_token)
        except ValueError:
            pass

        if qty_ == 0:
            bal = self.balance(to_checksum_address(input_token))
            qty_ = bal
            self._print.normal(f'No quantity give, so swap entire raw balance of: {bal}')
        self._print.debug(f'Quote Qty is: {qty_}')
        if self.version == 3:
            return self.quote_v3(input_token=input_token, output_token=output_token, out_decimals=out_decimals,
                                 raw_qty=qty_)
        elif self.version == 2:
            return self.quote_v2(input_token=input_token, output_token=output_token, out_decimals=out_decimals,
                                 raw_qty=qty_)

    def swap(self, input_token: str, output_token: str, float_qty: (float, int) = 0, raw_qty: int = 0, recipient: str = None,
             no_prompt: bool = False, fee_on_transfer: bool = False, _quote_only: bool = False) -> (bool, hex):
        """
        Main logic function. First, verify the input is correct. Then perform a quote, and ask the user to accept
        unless no_prompt is enabled. Finally, execute trade and return hex txid.

        :param _quote_only:
        :param fee_on_transfer:
        :param input_token: token to sell
        :param output_token: token to buy
        :param float_qty: float point qty
        :param raw_qty: integer raw qty
        :param recipient: optional alternative receiving address
        :param no_prompt: do not confirm quote, just trade
        :return: (bool, hex txid)
        """
        if self.debug_mode:
            self._print.debug('Function `swap` called with arguments: `%s %s %s %s %s %s %s %s`' % (input_token, output_token, float_qty, raw_qty, recipient, no_prompt, fee_on_transfer, _quote_only))
        self.eth_balance = self.w3.eth.get_balance(self.account.address)
        self._print.normal(f'ETH {self.native_assets} balance of this account: {self.eth_balance}')
        for x, param in enumerate([input_token, output_token]):
            if is_valid_evm_address(param):
                pass
            else:
                if x == 0:
                    input_token = input_token.upper()
                else:
                    output_token = output_token.upper()

        input_symbol, input_decimals, input_token, output_token, out_symbol, out_decimals = self.verify(input_token,
                                                                                                        output_token)
        if self.debug_mode:
            self._print.debug('Verify: %s %s %s %s %s %s' % (input_symbol, input_decimals, input_token, output_token, out_symbol, out_decimals))
        _qty = 0
        if raw_qty > 0:
            _qty = raw_qty
        if float_qty > 0:
            _qty = float_qty * 10 ** input_decimals

        if float_qty == 0.0:
            bal = self.balance(input_token, self.account.address)
            _qty = bal
            self._print.normal(f'Qty is Full Balance: {bal / 10 ** input_decimals}')
        else:
            self._print.normal(f'Qty is : {_qty}')
        quote = self.quote(input_token, output_token, qty_=int(_qty), symbol=input_symbol, decimals=input_decimals,
                           out_symbol=out_symbol, out_decimals=out_decimals)
        if not quote:
            return False
        else:
            if _quote_only:
                return quote
        self._print.normal(f'Quote is {quote}')
        if not no_prompt:

            prompt = input('>> Accept? y/n: ')
            if prompt == 'y':
                return self.uniswap.make_trade(input_token, output_token, _qty, recipient=recipient,
                                               fee_on_transfer=fee_on_transfer)
            else:
                self._print.warning('Canceled by user.')
                return 2
        else:
            self._print.warning('Prompt confirm quote disabled, firing away  .. ')
            return self.uniswap.make_trade(input_token, output_token, _qty, recipient=recipient,
                                           fee_on_transfer=fee_on_transfer)


if __name__ == '__main__':
    dotenv.load_dotenv()

    s = style.PrettyText()
    args = argparse.ArgumentParser(usage='pySwap Usage. See docs for details.')
    args.add_argument('-N', '--network', dest='network_name', default='ethereum', choices=['ethereum', 'polygon'],
                      help='The network to connect to.')
    args.add_argument('-uv', '--uniswap_version', type=int, default=2, choices=[2, 3], help='Uniswap version.')
    args.add_argument('-w', '--wallet', dest='wallet_file', type=str, default=None,
                      help='Location of json wallet file.')
    args.add_argument('-k', '--private_key', dest='private_key', default=None, help='Specify a private key directly')
    args.add_argument('-b', '--backend', type=str, choices=['sushiswap', 'uniswap', 'kyberswap'], default='uniswap',
                      help='Dex to connect to.')
    args.add_argument('-d', '--debug', action='store_true', help='Enable some developer features.')
    subparsers = args.add_subparsers(dest='command')
    cmd_quote = subparsers.add_parser('quote', help='Get a quote for a given swap.')
    cmd_quote.add_argument('-i', '--input', dest='input_token', type=str,
                           help='Contract address or known token symbol.')
    cmd_quote.add_argument('-o', '--output', dest='output_token', type=str,
                           help='Contract address or known token symbol.')
    cmd_quote.add_argument('-q', '--quantity', dest='quantity', type=float,
                           default=0.0, help='Float quantity.')
    cmd_quote.add_argument('-R', '--raw_quantity', dest='raw_quantity',
                           type=int, default=0, help='Raw quantity.')

    cmd_swap = subparsers.add_parser('swap', help='Perform a token swap.')
    cmd_swap.add_argument('-i', '--input', dest='input_token', type=str, help='Contract address or known token symbol.')
    cmd_swap.add_argument('-o', '--output', dest='output_token', type=str,
                          help='Contract address or known token symbol.')
    cmd_swap.add_argument('-q', '--quantity', dest='quantity', type=float, default=0.0, help='Float quantity.')
    cmd_swap.add_argument('-R', '--raw_quantity', dest='raw_quantity', type=int, default=0, help='Raw quantity.')
    cmd_swap.add_argument('-r', '--recipient', dest='recipient_address', type=str, help='Optional destination address.')
    cmd_swap.add_argument('-tf', '--transfer-fee', dest='enable_fee_on_transfer', action='store_true',
                          help='Use SupportingFeeOnTransfer swap')
    cmd_swap.add_argument('-n', '--no_prompt', dest='no_prompt', action='store_true',
                          help='Do not prompt to confirm quote.')

    qty = 0
    private_key = None
    address = None
    quote_only = False
    args = args.parse_args()

    if not args.wallet_file:
        wallet_file = os.environ.get('default_wallet_location')
    else:
        wallet_file = args.wallet_file
    if args.private_key and args.wallet_file:
        s.error('Either specify either a json wallet file or a private key, or set `default_wallet_location` in your '
                '`.env` file')
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

    uni = Swapper(private_key, address, version=int(args.uniswap_version), network=args.network_name,
                  backend=args.backend, debug=args.debug)
    if uni.uniswap is None:
        print('Uniswap not configured successfully , exiting')
        exit(1)

    if args.command == 'swap' or args.command == 'quote':
        if args.quantity and args.raw_quantity:
            s.error('Specify either a floating point quantity or a raw integer quantity, not both.')
            exit(1)
        if args.command == 'quote':
            quote_only = True

        if not hasattr(args, 'recipient_address'):
            setattr(args, 'recipient_address', address)
        if not hasattr(args, 'no_prompt'):
            setattr(args, 'no_prompt', False)
        if not hasattr(args, 'enable_fee_on_transfer'):
            setattr(args, 'enable_fee_on_transfer', False)

        for x, argument in enumerate(['input_token', 'output_token']):
            if getattr(args, argument) is None and x == 0:
                setattr(args, 'input_token', 'WETH')
            if getattr(args, argument) is None and x > 0:
                setattr(args, 'output_token', 'USDC')
        s.normal(
            f'Params: IN: {args.input_token}, OUT: {args.output_token}, QTY: {args.quantity}, RAW: {args.raw_quantity}')


        txid = uni.swap(input_token=args.input_token, output_token=args.output_token, float_qty=args.quantity, raw_qty=args.raw_quantity, recipient=args.recipient_address,
                        no_prompt=args.no_prompt, fee_on_transfer=args.enable_fee_on_transfer, _quote_only=quote_only)
        if txid == 2:
            exit(0)
        if type(txid) is float:
            exit(0)
        else:
            print(txid)
            if txid:
                tx_hex = to_hex(txid)
                s.good(f'TXID: {tx_hex} found, polling ...')
                uni.poll_tx_for_receipt(tx_hex)
            else:
                s.error('Some Error Occurred.')
    else:
        print('[?] No command given. Please run %s --help' % sys.argv[0])
