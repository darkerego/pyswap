#!/usr/bin/env python3
import argparse
import json
import os

from eth_utils import to_checksum_address

import lib.abi_lib
import zrx_swap
import web3
import dotenv


arb_token = '0x912CE59144191C1204E64559FE8253a0e49E6548'
weth = '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1'
wallet_file = 'keys/wallet.json'
dotenv.load_dotenv()
w3 = web3.Web3(web3.HTTPProvider(os.environ.get('arbitrum_http_endpoint')))
with open(wallet_file, 'r') as f:
    wallet = json.load(f).get('wallet')
    print(wallet)

address = wallet.get('address')
account = w3.eth.account.from_key(wallet.get('private_key'))
api = zrx_swap.ZeroX('arbitrum', False, None, wallet_file)


def get_balance():
    contract = w3.eth.contract(to_checksum_address(arb_token), abi=lib.abi_lib.EIP20_ABI)
    return contract.functions.balanceOf(address).call()


def main(_args):
    balance = get_balance()
    print(balance)
    human_balance = balance / (10 ** 18)

    print(f'[+] Balance: {human_balance}')
    if args.sell:
        api.swap(weth, arb_token, balance)
    if args.quote:
        api.quote(weth, arb_token, balance, True)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('-q', '--quote', action='store_true')
    args.add_argument('-s', '--sell', action='store_true')
    args = args.parse_args()
    main(args)
