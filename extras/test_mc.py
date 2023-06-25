# assuming you are on kovan
import os

import web3
from multicall import Multicall, Call
from web3 import Web3
w3=Web3(web3.HTTPProvider('https://mainnet.infura.io/v3/52f5c5e784084cda96d25869c09704ef'))
w3.isConnected()
DAI_TOKEN = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
MKR_WHALE = '0xdb33dfd3d61308c33c63209845dad3e6bfb2c674'
MKR_FISH = '0x518e6C7FeBa748ae32bCe650fD266DF1EBfbFF71'


def from_wei(value):
    return value / 1e18


multi = Multicall(calls=[
    Call(DAI_TOKEN, ['balanceOf(address)(uint256)', MKR_WHALE], [['whale', from_wei]]),
    Call(DAI_TOKEN, ['balanceOf(address)(uint256)', MKR_FISH], [['fish', from_wei]]),
    Call(DAI_TOKEN, 'totalSupply()(uint256)', [['supply', from_wei]])
],_w3=w3)

ret=multi()  # {'whale': 566437.0921992733, 'fish': 7005.0, 'supply': 1000003.1220798912}
print(ret)

# seth-style calls
r=Call(DAI_TOKEN, ['balanceOf(address)(uint256)', MKR_WHALE], _w3=w3)()
print((r))
Call(DAI_TOKEN, 'balanceOf(address)(uint256)')([MKR_WHALE],_w3=w3)
# return values processing
Call(DAI_TOKEN, 'totalSupply()(uint256)', [['supply', from_wei]], _w3=w3)()
