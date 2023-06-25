#!/usr/bin/env python3
############################
import argparse
import json
import os
import pprint
import time

import dotenv
import requests
import web3
from web3.middleware import geth_poa_middleware

import lib.abi_lib
from lib import style

# Hacky fix because I was using the beta web3 which has clumsy backward compatibility issues
try:
    from eth_utils.address import toCheckSumAddress as to_checksum_address
except ImportError:
    from eth_utils.address import to_checksum_address

try:
    from eth_utils.curried import toHex as to_hex
except ImportError:
    from eth_utils.curried import to_hex

try:
    from eth_utils.curried import toWei as to_wei
except ImportError:
    from eth_utils.curried import to_wei
dotenv.load_dotenv()


class ZeroX:
    def __init__(self, network: str, no_prompt=False, privkey_str: str = None, wallet_file: str = None):
        self._print = style.PrettyText()
        self.network = network
        self.endpoint = None
        self.abi = None
        self.w3 = self.setup_w3()
        self.exchange_router = '0xDef1C0ded9bec7F1a1670819833240f027b25EfF'
        self.no_prompt = no_prompt

        self._session = requests.session()
        self.acct = None
        if privkey_str and wallet_file:
            self._print.error('Specify either a privkey str or a json wallet file, not both!')
        if privkey_str and not wallet_file:  # Store key in memory encoded to maybe prevent some really dumb hackers
            #  from trying to do something, idk.
            self.acct = self.w3.eth.account.from_key(privkey_str)
        if wallet_file and not privkey_str:
            self._privkey, self._address = self.load_wallet(wallet_file)
            self.acct = self.w3.eth.account.from_key(self._privkey)

    def load_wallet(self, location):
        with open(location, 'r') as f:
            gas_wal = json.load(f)
            addr = gas_wal.get('wallet').get('address')
            priv = gas_wal.get('wallet').get('private_key')
            del f
            return priv, addr

    def setup_w3(self, ):
        w3_endpoint = os.environ.get(f'{self.network}_http_endpoint')
        self.w3 = web3.Web3(web3.HTTPProvider(w3_endpoint))
        try:
            conn = self.w3.isConnected()
        except AttributeError:
            conn = self.w3.is_connected()
        finally:
            if conn:
                self._print.good(f"Connected to chain: {self.w3.eth.chain_id}")
            else:
                self._print.error(f'Web3 could connect to remote endpoint: {w3_endpoint}')
        if self.network == 'ethereum':
            self.endpoint = 'https://api.0x.org/'
            self.abi = lib.abi_lib.EIP20_ABI
        elif self.network == 'polygon':
            self.endpoint = 'https://polygon.api.0x.org/'
            self.abi = lib.abi_lib.EIP20_ABI
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        elif self.network == 'bsc':
            self.abi = lib.abi_lib.BEP_ABI
            # self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            self.endpoint = 'https://bsc.api.0x.org/'
            self._print.warning('Connected to BSC, which has not been tested very well yet.')
        elif self.network == 'arbitrum':
            self.abi = lib.abi_lib.EIP20_ABI
            self.endpoint = 'https://arbitrum.api.0x.org/'

        self._print.good(f'Web3 connected to chain: {self.w3.eth.chain_id}')
        return self.w3

    def balance_check(self, contract_address: str = None):
        if not contract_address:
            bal = self.w3.eth.get_balance(self.acct.address)
            return bal, bal / 10 ** 18
        else:
            contract = self.w3.eth.contract(address=to_checksum_address(contract_address),
                                            abi=lib.abi_lib.BEP_ABI)
            decimals = contract.functions.decimals().call()
            balance = contract.functions.balanceOf(self.acct.address).call()
            human_bal = balance / (10 ** decimals)
            return balance, human_bal

    def broadcast_tx(self, raw_txn: dict):
        raw_txn['nonce'] = self.w3.eth.get_transaction_count(self.acct.address)
        signed_txn = self.w3.eth.account.signTransaction(raw_txn, self.acct.key)
        try:
            ret = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        except ValueError as err:
            self._print.error(f'Error sending: {err}')
            hextx = False
        else:
            hextx = to_hex(ret)
            self._print.good(f'Transaction sent okay! Txid is: {hextx}')
        return hextx

    def poll_receipt(self, tx_hash):
        poll = 0
        time.sleep(1)
        start = time.time()
        while True:
            if poll > 100:
                break
            poll += 1
            self._print.normal(f'Polling for receipt: {poll}/100 ... ')
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            except web3.exceptions.TransactionNotFound:
                time.sleep(1)
            else:
                receipt = receipt.__dict__
                pprint.pprint(receipt)
                end = time.time()
                elapsed = end - start
                self._print.good(f'Confirmed in {elapsed} secs!')
                return receipt
        print('Timed Out!')

    def approve(self, token, amount=0):
        spender = self.exchange_router
        if not amount:
            max_amount = to_wei(2 ** 64 - 1, 'ether')
        else:
            max_amount = amount
        contract = self.w3.eth.contract(to_checksum_address(token), abi=lib.abi_lib.BEP_ABI)
        if self.network == 'bsc':
            tx = {
                'from': self.acct.address,
                'nonce': self.w3.eth.get_transaction_count(self.acct.address),
                'gas': 250000,
                'gasPrice': self.w3.eth.gas_price
            }
        else:
            tx = {
                'from': self.acct.address,
                'nonce': self.w3.eth.get_transaction_count(self.acct.address),
                'gas': 250000,
            }

        tx = contract.functions.approve(to_checksum_address(spender), max_amount).build_transaction(tx)
        return self.broadcast_tx(raw_txn=tx)

    def quote(self, buy_token: str, sell_token: str, raw_amount: int, quote_only=False):
        params = {'sellToken': sell_token, 'buyToken': buy_token, 'sellAmount': raw_amount,
                  'takerAddress': self.acct.address}
        self._print.normal(f'Get quote for IN: {sell_token}, OUT: {buy_token}')
        if quote_only:
            params.pop('takerAddress')
        resp = self._session.get(self.endpoint + 'swap/v1/quote', params=params)
        if resp.status_code == 200:
            return resp.json()
        else:
            if resp.status_code == 400:
                print(resp.text)
                if not quote_only:
                    self._print.error('ERROR: Is the token approved?')
                    return False
                    # ret = self.approve(sell_token)
                    # self.poll_receipt(ret)
                    # self.quote(buy_token, sell_token, raw_amount)

            self._print.warning(f'Non 200 response from 0x api: {resp.text}')
            return False

    def swap(self, buy_token, sell_token, raw_amount):
        assert type(raw_amount) is int
        assert type(buy_token) is str
        assert type(sell_token) is str
        obj = self.quote(buy_token, sell_token, raw_amount)
        obj = dict(obj)
        pprint.pprint(obj)
        tx = {
            "from": self.acct.address,
            "gas": hex(int(200000)),
            "gasPrice": hex(int(obj.get('gasPrice'))),
            "to": to_checksum_address(obj.get('to')),
            "value": hex(int(obj.get('value'))),
            "data": obj.get('data'),
            "nonce": self.w3.eth.get_transaction_count(self.acct.address),
            "chainId": self.w3.eth.chain_id
        }
        pprint.pprint(tx)
        self.w3.eth.estimate_gas(tx)
        if obj:
            pprint.pprint(obj)
            if not self.no_prompt:
                confirm = input('Accept this quote?')
                if confirm.upper() == 'Y' or confirm.upper() == 'YES':
                    self._print.normal('Broadcasting transaction ... ')
                    self.broadcast_tx(tx)
                else:
                    self._print.normal('Operation canceled by user.')
            else:
                self._print.normal('Broadcasting transaction ... ')
                self.broadcast_tx(tx)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('-n', '--network', dest='network_name', type=str, choices=['ethereum', 'polygon', 'bsc', 'arbitrum'],
                      default='ethereum', help='The network to connect to.')
    args.add_argument('-Q', '--quote', dest='quote_only', action='store_true',
                      help='Only quote, do not transact.')
    args.add_argument('-F', '--force', dest='no_prompt', action='store_true',
                      help='Do not prompt to accept quote, just go ahead and swap. For use in scripts.')
    args.add_argument('-k', '--key', dest='privkey_as_str', type=str, default=None, help='Specify a privkey.')
    args.add_argument('-w', '--wallet', dest='json_wallet_file', type=str, default=None,
                      help='Location of json wallet.')
    args.add_argument('-i', '--input_token', type=str, help='Sell token.')
    args.add_argument('-o', '--output_token', type=str, help='Buy token.')
    args.add_argument('-b', '--balance', dest='balance_check', type=str, default=False,
                      help='Check balance of this contract.')
    args.add_argument('-nb', '--native_balance', action='store_true')
    args.add_argument('-q', '--quantity', type=int, help='Raw Integer Quantity to swap.')
    args = args.parse_args()

    if not args.privkey_as_str and not args.json_wallet_file:
        default_wallet = os.environ.get('default_wallet_location')
        if default_wallet:
            setattr(args, 'json_wallet_file', default_wallet)
    api = ZeroX(args.network_name, args.no_prompt, args.privkey_as_str, args.json_wallet_file)
    api._print.good(f'API Configured, Network: {args.network_name}, Force: {args.no_prompt}, '
                    f'Wallet: {args.json_wallet_file}')
    if args.native_balance:
        raw, human = api.balance_check(contract_address=None)
        api._print.good(f'Balance: {human}, Raw: {raw}')
    if args.balance_check and type(args.balance_check) is not bool:
        raw, human = api.balance_check(args.balance_check)
        api._print.good(f'Balance: {human}, Raw: {raw}')
    unlimited_approvals = os.environ.get('unlimited_approvals')
    if unlimited_approvals:
        api._print.warning('Warning: Unlimited Token Approvals Enabled.')
    if args.input_token and args.output_token:
        if not args.quote_only:
            api.swap(to_checksum_address(args.output_token), to_checksum_address(args.input_token), args.quantity)
        else:
            quote = api.quote(args.output_token, args.input_token, args.quantity, args.quote_only)
            pprint.pprint(quote)
