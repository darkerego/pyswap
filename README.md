# Python Command Line Dex Swap Tool

### Changelog

<p>
<b>
New Release ~ 6/25/23

- Many bugfixes
- argparse is now more intuitive
- check back soon, I am going to add out of box support for many more chains!

</b>
</p>

<p>
Swap assets on uniswap, sushiswap, and kyberswap. Easily can be modified 
to support any dex that is a direct fork of uniswap by modifying the 
json file `data/dex_contracts.json`.
</p>

### Demo 

<p>
This asciinema demonstrates swapping DAI to WMATIC (wrapped matic) on 
kyberswap. Note that sometimes dexes are weird about native assets that are 
not Ethereum, so you may have to swap your assets into a wrapped asset in 
order to do this programatically. I am not sure why that is, but solving 
it is one of the things on the TODO list.
</p>

[![asciicast](https://asciinema.org/a/ZhXtuUkOnXUbzznqEwrKNqZ86.svg)](https://asciinema.org/a/ZhXtuUkOnXUbzznqEwrKNqZ86)

<pre>
usage: Pyswap Usage. See docs for details.

usage: pySwap Usage. See docs for details.

positional arguments:
  {quote,swap}
    quote               Get a quote for a given swap.
    swap                Perform a token swap.

options:
  -h, --help            show this help message and exit
  -N {ethereum,polygon}, --network {ethereum,polygon}
                        The network to connect to.
  -uv {2,3}, --uniswap_version {2,3}
                        Uniswap version.
  -w WALLET_FILE, --wallet WALLET_FILE
                        Location of json wallet file.
  -k PRIVATE_KEY, --private_key PRIVATE_KEY
                        Specify a private key directly
  -b {sushiswap,uniswap,kyberswap}, --backend {sushiswap,uniswap,kyberswap}
                        Dex to connect to.
  -d, --debug           Enable some developer features.


</pre>

### Configuration
<p>
<b>To get running ... </b>

- Copy .env.example to .env and put your 
infura endpoints in there
- Copy example_wallet.json to keys/default_wallet.json and add your address and key.
-  

      -  FYI: If you want a cool vanity address like this one: 0xffffad719353ff7cba6c1799deae8ad8d94d8724 , check out my vanity address generator: https://github.com/darkerego/ethervain
- To add more known tokens that can be referanced by name, 
just add them to data/tokens_ethereum.json and data/tokens_polygon.json
</p>


### TOOD

- Figure out why in some cases we cannot swap native assets other than ETH