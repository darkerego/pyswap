# Python Command Line Dex Swap Tool

<p>
Swap assets on uniswap, sushiswap, and kyberswap. Easily can be modified 
to support any dex that is a direct fork of uniswap by modifying the 
json file `data/dex_contracts.json`.
</p>

<pre>
usage: Pyswap Usage. See docs for details.

options:
  -h, --help            show this help message and exit
  -i INPUT_TOKEN, --input INPUT_TOKEN
                        Contract address or known token symbol.
  -o OUTPUT_TOKEN, --output OUTPUT_TOKEN
                        Contract address or known token symbol.
  -q QUANTITY, --quantity QUANTITY
                        Float quantity.
  -R RAW_QUANTITY, --raw_quantity RAW_QUANTITY
                        Raw quantity.
  -r RECIPIENT_ADDRESS, --recipient RECIPIENT_ADDRESS
                        Optional destination address.
  -n, --no_prompt       Do not prompt to confirm quote.
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

</pre>

### Configuration
<p>

- To get running you only need to copy .env.example to .env and put your 
infura endpoints in there. 

- To add more known tokens that can be referanced by name, 
just add them to data/tokens_ethereum.json and data/tokens_polygon.json
</p>