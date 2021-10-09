from time import sleep
import io
import asyncpg
import discord
from discord.ext import tasks, commands

from datetime import datetime
from discord.message import Attachment
import requests
import json
import configparser

OPENSEA_API_EVENTS_URL = "https://api.opensea.io/api/v1/events"

class Tracker():
    def get_bids(self) -> dict:
        to_ret = {}
        request_url = f'''{OPENSEA_API_EVENTS_URL}?asset_contract_address={self.collection_contract_address}&event_type=offer_entered&format=json'''

        events = requests.request("GET", request_url).json()
        for event in events["asset_events"]:
            event_date = event["created_date"]
            asset_name = event["asset"]["name"]
            token_id = event["asset"]["token_id"]
            total_price = int(event["bid_amount"])
            payment_token_decimals = int(event["payment_token"]["decimals"])
            payment_token_symbol = event["payment_token"]["symbol"]
            image_url = event["asset"]["image_thumbnail_url"]

            date_time = datetime.strptime(event_date, '%Y-%m-%dT%H:%M:%S.%f')
            if token_id in to_ret.keys():
                if date_time < to_ret[token_id]['date_time']:
                   pass
            else:
                 to_ret.update({token_id: { "date_time": date_time,
                                            "asset_name": asset_name,
                                            "total_price": total_price,
                                            "payment_token_decimals": payment_token_decimals,
                                            "payment_token_symbol" : payment_token_symbol,
                                            "image_url": image_url}})
        return to_ret

    def get_sales(self) -> dict:
        to_ret = {}
        request_url = f'''{OPENSEA_API_EVENTS_URL}?asset_contract_address={self.collection_contract_address}&event_type=successful&format=json'''

        events = requests.request("GET", request_url).json()
        for event in events["asset_events"]:
            event_date = event["created_date"]
            asset_name = event["asset"]["name"]
            token_id = event["asset"]["token_id"]
            total_price = int(event["total_price"])
            payment_token_decimals = int(event["payment_token"]["decimals"])
            payment_token_symbol = event["payment_token"]["symbol"]
            image_url = event["asset"]["image_thumbnail_url"]

            date_time = datetime.strptime(event_date, '%Y-%m-%dT%H:%M:%S.%f')

            if token_id in to_ret.keys() :
                if date_time < to_ret[token_id]['date_time']:
                   pass
            else:
                 to_ret.update({token_id: { "date_time": date_time,
                                            "asset_name": asset_name,
                                            "total_price": total_price,
                                            "payment_token_decimals": payment_token_decimals,
                                            "payment_token_symbol" : payment_token_symbol,
                                            "image_url": image_url}})
        return to_ret
    
    def __init__(self, collection_contract_address) -> None:
        self.collection_contract_address = collection_contract_address

        self.last_bids  = self.get_bids()
        self.last_sales = self.get_sales()

    def get_new_bids(self) -> dict:
        bids = self.get_bids()
        new_bids = {k: bids[k] for k in bids if (k in self.last_bids and bids[k] != self.last_bids[k]) or (k not in self.last_bids)}
        self.last_bids = bids
        return new_bids

    def get_new_sales(self) -> dict:
        sales = self.get_sales()
        new_sales = {k: sales[k] for k in sales if (k in self.last_sales and sales[k] != self.last_sales[k]) or (k not in self.last_sales)}
        self.last_sales = sales
        return new_sales

class Config:
    def __init__(self) -> None:
        config = configparser.ConfigParser()
        config.read('opensea_tracker.config')

        # parse the config
        self.DISCORD_BOT_TOKEN              = str(config['DEFAULT']['DiscordBotToken'])
        self.DISCORD_CHANNEL_ID             = int(config['DEFAULT']['DiscordChannelId'])
        self.ASSET_CONTRACTS_TO_SCAN        = list(filter(None, str(config['DEFAULT']['AssetContractsToScan']).replace('\n','').split(sep=';')))
        self.PING_INTERVAL_IN_SEC           = float(config['DEFAULT']['PingIntervalInSec'])
        self.BO_PRINT_SALES_TO_CONSOLE      = str(config['DEFAULT']['BoPrintSalesToConsole'])
        self.BO_PRINT_BIDS_TO_CONSOLE       = str(config['DEFAULT']['BoPrintBidsToConsole'])
    def print(self):
        print('\n\n\n------------------------------------[ config ]------------------------------------')
        print(f'[C] Discord bot token:         {self.DISCORD_BOT_TOKEN}')
        print(f'[C] Discord channel id:        {self.DISCORD_CHANNEL_ID}')
        print(f'[C] Asset adresses to scan:    ')
        for contract in self.ASSET_CONTRACTS_TO_SCAN:
            print(f'[->]\t{contract}')
        print(f'[C] Ping interval (seconds):   {self.PING_INTERVAL_IN_SEC}')
        print(f'[BO] Print sales to console:   {self.BO_PRINT_SALES_TO_CONSOLE}')
        print(f'[BO] Print bids to console:    {self.BO_PRINT_BIDS_TO_CONSOLE}')
        print('----------------------------------------------------------------------------------\n\n\n')



conf = Config()
conf.print()

client = discord.Client()


class OpenseaTrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker_printer.add_exception_type(asyncpg.PostgresConnectionError)

        self.trackers = []
        for contract in conf.ASSET_CONTRACTS_TO_SCAN:
            self.trackers.append(Tracker(contract))
        self.tracker_printer.start()

    def cog_unload(self):
        self.tracker_printer.cancel()

    @tasks.loop(seconds=conf.PING_INTERVAL_IN_SEC)
    async def tracker_printer(self):
        channel = client.get_channel(conf.DISCORD_CHANNEL_ID)
        all_sales_message = '========[ sales ]========\n'
        all_bids_message =  '========[ bids  ]========\n'

        for tracker in self.trackers:
            
            sales = tracker.get_sales()
            bids = tracker.get_bids()

            for key in sales.keys():
                price_in_token = sales[key]['total_price']/(10**sales[key]['payment_token_decimals'])
                all_sales_message = all_sales_message + (f"[ SALE @ {sales[key]['date_time'].isoformat(' ', 'seconds')} ]\t{sales[key]['asset_name']}\tfor\t{price_in_token} {sales[key]['payment_token_symbol']}\n")
            for key in bids.keys():
                price_in_token = bids[key]['total_price']/(10**bids[key]['payment_token_decimals'])
                all_bids_message = all_bids_message + (f"[ BID @ {bids[key]['date_time'].isoformat(' ', 'seconds')} ]\t{bids[key]['asset_name']}\tfor\t{price_in_token} {bids[key]['payment_token_symbol']}\n")

            new_bids = tracker.get_new_bids()
            new_sales = tracker.get_new_sales()
 
            if new_bids:
                for key in new_bids.keys():
                    price_in_token = new_bids[key]['total_price']/(10**new_bids[key]['payment_token_decimals'])
                    image_raw = io.BytesIO(requests.get(new_bids[key]["image_url"], allow_redirects=True).content)
                    await channel.send( f"```[ BID @ {new_bids[key]['date_time'].isoformat(' ', 'seconds')} ]\t{new_bids[key]['asset_name']}\tfor\t{price_in_token} {new_bids[key]['payment_token_symbol']}\n```",
                                        file=discord.File(fp=image_raw, filename="thumbnail.png"))
                    
            if new_sales:
                for key in new_sales.keys():
                    price_in_token = new_sales[key]['total_price']/(10**new_sales[key]['payment_token_decimals'])
                    image_raw = io.BytesIO(requests.get(new_sales[key]["image_url"], allow_redirects=True).content)
                    await channel.send( f"```[ SALE @ {new_sales[key]['date_time'].isoformat(' ', 'seconds')} ]\t{new_sales[key]['asset_name']}\tfor\t{price_in_token} {new_sales[key]['payment_token_symbol']}```\n",
                                        file=discord.File(fp=image_raw, filename="thumbnail.png"))

        if conf.BO_PRINT_SALES_TO_CONSOLE:
            print(all_sales_message)
        if conf.BO_PRINT_BIDS_TO_CONSOLE:
            print(all_bids_message)
                

    @tracker_printer.before_loop
    async def before_tracker_printer(self):
        print('Launching...')
        await self.bot.wait_until_ready()


@client.event
async def on_ready():
    print(f"[.] Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if message.content.startswith('$hello_OSTB'):
        await message.channel.send(f'Hello {message.author.name}')

OpenseaTrackerCog(client)
client.run(conf.DISCORD_BOT_TOKEN)