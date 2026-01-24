from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp
import asyncio
import os
import json
import time
import aiofiles

@register("astrbot_plugin_crypto_asset", "Arturia169", "astrbot_plugin_crypto_asset 是一个功能强大的 AstrBot 插件，专为加密货币用户设计。它不仅支持实时查询全网虚拟币价格，还具备多链钱包地址转账监控功能，让您随时随地掌握链上动态。", "1.2.0", "https://github.com/Arturia169/astrbot_plugin_crypto_asset")
class CryptoPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.api_url = "https://api.coingecko.com/api/v3"
        
        # 链配置
        self.chains = {
            "eth": {
                "name": "Ethereum",
                "api_url": "https://api.etherscan.io/api",
                "scan_url": "https://etherscan.io",
                "key_config": "etherscan_api_key",
                "symbol": "ETH"
            },
            "arb": {
                "name": "Arbitrum",
                "api_url": "https://api.arbiscan.io/api",
                "scan_url": "https://arbiscan.io",
                "key_config": "arbiscan_api_key",
                "symbol": "ETH"
            },
            "op": {
                "name": "Optimism",
                "api_url": "https://api-optimistic.etherscan.io/api",
                "scan_url": "https://optimistic.etherscan.io",
                "key_config": "optimism_api_key",
                "symbol": "ETH"
            },
            "base": {
                "name": "Base",
                "api_url": "https://api.basescan.org/api",
                "scan_url": "https://basescan.org",
                "key_config": "basescan_api_key",
                "symbol": "ETH"
            },
            "tron": {
                "name": "Tron",
                "api_url": "https://api.trongrid.io/v1",
                "scan_url": "https://tronscan.org/#",
                "key_config": "trongrid_api_key",
                "symbol": "TRX"
            }
        }
        
        # 数据存储路径
        # 尝试使用 context 获取数据目录（如果框架支持），否则回退到标准路径
        # 假设 context 中可能没有直接的 data_dir，这里使用相对路径确保兼容性
        self.data_dir = os.path.join(os.getcwd(), 'data', 'astrbot_plugin_crypto_asset_data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.wallets_file = os.path.join(self.data_dir, 'wallets.json')
        
        self.wallets = {}
        # 启动初始化和监控任务
        # 使用 create_task 确保不阻塞 __init__
        self.monitor_task = asyncio.create_task(self.monitor_loop())

    async def load_wallets(self):
        if os.path.exists(self.wallets_file):
            try:
                async with aiofiles.open(self.wallets_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"加载钱包数据失败: {e}")
                return {}
        return {}

    async def save_wallets(self):
        try:
            async with aiofiles.open(self.wallets_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.wallets, indent=4, ensure_ascii=False))
        except Exception as e:
            logger.error(f"保存钱包数据失败: {e}")

    async def terminate(self):
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

    async def monitor_loop(self):
        # 在循环开始前加载数据
        self.wallets = await self.load_wallets()
        logger.info(f"虚拟币转账监控任务已启动 (多链版)，加载了 {len(self.wallets)} 个用户的配置")
        
        while True:
            try:
                interval = self.config.get("check_interval", 60)
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    for user_id, user_wallets in list(self.wallets.items()): # 使用 list 避免迭代时修改
                        for address, info in list(user_wallets.items()):
                            chain = info.get("chain", "eth")
                            if chain not in self.chains:
                                continue
                            
                            key_config_name = self.chains[chain]["key_config"]
                            api_key = self.config.get(key_config_name)
                            
                            if not api_key:
                                continue

                            if chain == "tron":
                                await self.check_tron(session, user_id, address, info, api_key)
                            else:
                                await self.check_evm(session, user_id, address, info, api_key, chain)
                                
                            await asyncio.sleep(0.5) # 基础频率限制
                            
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(60)

    async def check_evm(self, session: aiohttp.ClientSession, user_id: str, address: str, info: dict, api_key: str, chain: str):
        chain_conf = self.chains[chain]
        last_block = info.get("last_block", 0)
        
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": last_block + 1,
            "sort": "asc",
            "apikey": api_key
        }
        
        try:
            async with session.get(chain_conf["api_url"], params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"{chain} API Error: {resp.status}")
                    return
                
                data = await resp.json()
                
                if data.get("status") == "1" and data.get("result"):
                    txs = data["result"]
                    new_last_block = last_block
                    
                    for tx in txs:
                        if int(tx["value"]) == 0:
                            new_last_block = max(new_last_block, int(tx["blockNumber"]))
                            continue
                            
                        await self.notify_user_evm(user_id, address, info.get("remark", ""), tx, chain)
                        new_last_block = max(new_last_block, int(tx["blockNumber"]))
                    
                    if new_last_block > last_block:
                        self.wallets[user_id][address]["last_block"] = new_last_block
                        await self.save_wallets()
                    
        except Exception as e:
            logger.error(f"监控 EVM 地址 {address} ({chain}) 出错: {e}")

    async def check_tron(self, session: aiohttp.ClientSession, user_id: str, address: str, info: dict, api_key: str):
        chain_conf = self.chains["tron"]
        last_ts = info.get("last_timestamp", 0)
        
        url = f"{chain_conf['api_url']}/accounts/{address}/transactions"
        params = {
            "only_confirmed": "true",
            "limit": 20,
            "order_by": "block_timestamp,asc",
            "min_timestamp": last_ts + 1
        }
        headers = {"TRON-PRO-API-KEY": api_key}
        
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200: return
                
                data = await resp.json()
                
                if data.get("success") and data.get("data"):
                    txs = data["data"]
                    new_last_ts = last_ts
                    
                    for tx in txs:
                        block_ts = tx.get("block_timestamp", 0)
                        
                        raw_data = tx.get("raw_data", {})
                        contract = raw_data.get("contract", [])[0]
                        if contract.get("type") == "TransferContract":
                            value = contract["parameter"]["value"]["amount"]
                            await self.notify_user_tron(user_id, address, info.get("remark", ""), tx, value, "TRX")
                        
                        new_last_ts = max(new_last_ts, block_ts)
                    
                    if new_last_ts > last_ts:
                        self.wallets[user_id][address]["last_timestamp"] = new_last_ts
                        await self.save_wallets()
            
            await self.check_tron_trc20(session, user_id, address, info, api_key, last_ts)

        except Exception as e:
            logger.error(f"监控 Tron 地址 {address} 出错: {e}")

    async def check_tron_trc20(self, session: aiohttp.ClientSession, user_id: str, address: str, info: dict, api_key: str, last_ts: int):
        chain_conf = self.chains["tron"]
        url = f"{chain_conf['api_url']}/accounts/{address}/transactions/trc20"
        params = {
            "only_confirmed": "true",
            "limit": 20,
            "min_timestamp": last_ts + 1
        }
        headers = {"TRON-PRO-API-KEY": api_key}
        
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200: return
                data = await resp.json()
                
                if data.get("success") and data.get("data"):
                    txs = data["data"]
                    # 注意：这里应该读取最新的 last_timestamp，因为它可能在 check_tron 中被更新了
                    current_last_ts = self.wallets[user_id][address].get("last_timestamp", last_ts)
                    new_last_ts = current_last_ts
                    
                    for tx in txs:
                        block_ts = int(tx.get("block_timestamp", 0))
                        # 再次过滤，确保不重复处理
                        if block_ts <= last_ts:
                            continue

                        token_info = tx.get("token_info", {})
                        symbol = token_info.get("symbol", "Unknown")
                        decimals = int(token_info.get("decimals", 6))
                        value = int(tx.get("value", 0))
                        
                        real_value = value / (10 ** decimals)
                        
                        await self.notify_user_tron_trc20(user_id, address, info.get("remark", ""), tx, real_value, symbol)
                        
                        new_last_ts = max(new_last_ts, block_ts)
                        
                    if new_last_ts > current_last_ts:
                        self.wallets[user_id][address]["last_timestamp"] = new_last_ts
                        await self.save_wallets()
                    
        except Exception as e:
            logger.error(f"监控 Tron TRC20 出错: {e}")

    async def notify_user_evm(self, user_id: str, address: str, remark: str, tx: dict, chain: str):
        chain_conf = self.chains[chain]
        value = int(tx["value"]) / 10**18
        direction = "🟢 收到" if tx["to"].lower() == address.lower() else "🔴 发送"
        other_party = tx["from"] if direction == "🟢 收到" else tx["to"]
        other_party_short = f"{other_party[:6]}...{other_party[-4:]}"
        hash_short = f"{tx['hash'][:6]}...{tx['hash'][-4:]}"
        
        msg = (
            f"🔔 **{chain_conf['name']} 转账提醒**\n"
            f"钱包: {remark} ({address[:6]}...)\n"
            f"{direction}: {value:.4f} {chain_conf['symbol']}\n"
            f"对方: {other_party_short}\n"
            f"交易哈希: {hash_short}\n"
            f"[查看详情]({chain_conf['scan_url']}/tx/{tx['hash']})"
        )
        logger.info(f"Notify {user_id}: {msg}")

    async def notify_user_tron(self, user_id: str, address: str, remark: str, tx: dict, value: float, symbol: str):
        real_value = value / 10**6
        tx_id = tx["txID"]
        msg = (
            f"🔔 **Tron 转账提醒**\n"
            f"钱包: {remark} ({address[:6]}...)\n"
            f"交易金额: {real_value:.4f} {symbol}\n"
            f"交易哈希: {tx_id[:6]}...\n"
            f"[查看详情](https://tronscan.org/#/transaction/{tx_id})"
        )
        logger.info(f"Notify {user_id}: {msg}")

    async def notify_user_tron_trc20(self, user_id: str, address: str, remark: str, tx: dict, value: float, symbol: str):
        tx_id = tx["transaction_id"]
        direction = "🟢 收到" if tx["to"] == address else "🔴 发送"
        msg = (
            f"🔔 **Tron TRC20 提醒**\n"
            f"钱包: {remark} ({address[:6]}...)\n"
            f"{direction}: {value:.4f} {symbol}\n"
            f"交易哈希: {tx_id[:6]}...\n"
            f"[查看详情](https://tronscan.org/#/transaction/{tx_id})"
        )
        logger.info(f"Notify {user_id}: {msg}")

    @filter.command("watch")
    async def watch_wallet(self, event: AstrMessageEvent, address: str, remark: str = "默认钱包", chain: str = None):
        '''监控钱包。用法: /watch <地址> [备注] [chain]
        支持的 chain: eth (默认), arb, op, base, tron'''
        
        user_id = event.unified_msg_origin
        
        # 确保数据已加载
        if not hasattr(self, 'wallets'):
            self.wallets = {}

        if user_id not in self.wallets:
            self.wallets[user_id] = {}
            
        if address in self.wallets[user_id]:
            current_chain = self.wallets[user_id][address].get("chain", "eth")
            yield event.plain_result(f"该地址已在监控列表中 ({current_chain}): {address}")
            return

        target_chain = "eth"
        if address.startswith("T"):
            target_chain = "tron"
        elif chain:
            target_chain = chain.lower()
        
        if target_chain not in self.chains:
            yield event.plain_result(f"不支持的链: {target_chain}。支持: {', '.join(self.chains.keys())}")
            return

        key_config = self.chains[target_chain]["key_config"]
        api_key = self.config.get(key_config)
        
        if not api_key:
             yield event.plain_result(f"❌ 错误: 未配置 {target_chain} 的 API Key，无法添加监控。请联系管理员在配置中填写 {key_config}。")
             return

        start_point = 0
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                if target_chain == "tron":
                    start_point = int(time.time() * 1000)
                else:
                    url = self.chains[target_chain]["api_url"]
                    params = {"module": "proxy", "action": "eth_blockNumber", "apikey": api_key}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            d = await resp.json()
                            if "result" in d:
                                start_point = int(d["result"], 16)
        except Exception as e:
            logger.warning(f"获取初始状态失败: {e}")
            yield event.plain_result("⚠️ 获取初始区块失败，网络可能不稳定，但已尝试添加监控。")
            
        self.wallets[user_id][address] = {
            "chain": target_chain,
            "remark": remark,
            "last_block": start_point if target_chain != "tron" else 0,
            "last_timestamp": start_point if target_chain == "tron" else 0
        }
        await self.save_wallets()
        
        yield event.plain_result(f"✅ 已添加监控 ({self.chains[target_chain]['name']}):\n{remark}\n{address}")

    @filter.command("unwatch")
    async def unwatch_wallet(self, event: AstrMessageEvent, address: str):
        '''取消监控钱包。用法: /unwatch <地址>'''
        user_id = event.unified_msg_origin
        
        if user_id in self.wallets and address in self.wallets[user_id]:
            del self.wallets[user_id][address]
            await self.save_wallets()
            yield event.plain_result(f"🗑️ 已移除监控: {address}")
        else:
            yield event.plain_result(f"未找到该监控地址: {address}")

    @filter.command("wallets")
    async def list_wallets(self, event: AstrMessageEvent):
        '''列出所有监控的钱包'''
        user_id = event.unified_msg_origin
        
        if user_id not in self.wallets or not self.wallets[user_id]:
            yield event.plain_result("📭 你还没有监控任何钱包。使用 /watch 添加。")
            return
            
        msg = "📋 **监控列表**\n"
        for addr, info in self.wallets[user_id].items():
            chain_name = self.chains.get(info.get("chain", "eth"), {}).get("name", "Unknown")
            msg += f"- {info['remark']} ({chain_name})\n  `{addr}`\n"
            
        yield event.plain_result(msg)

    @filter.command("price")
    async def get_price(self, event: AstrMessageEvent, coin: str):
        '''查询虚拟币价格。用法: /price <币种名称或代码>'''
        if not coin:
            yield event.plain_result("请提供币种名称或代码，例如: /price BTC")
            return

        coin_name = coin.strip()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                search_url = f"{self.api_url}/search"
                async with session.get(search_url, params={"query": coin_name}) as resp:
                    if resp.status != 200:
                        yield event.plain_result("查询失败，API 服务暂时不可用。")
                        return
                    data = await resp.json()
                
                coins = data.get("coins", [])
                if not coins:
                    yield event.plain_result(f"未找到名为 {coin_name} 的虚拟币。")
                    return

                target_coin = coins[0]
                coin_id = target_coin["id"]
                symbol = target_coin["symbol"]
                name = target_coin["name"]

                price_url = f"{self.api_url}/simple/price"
                params = {
                    "ids": coin_id,
                    "vs_currencies": "usd,cny"
                }
                async with session.get(price_url, params=params) as resp:
                    if resp.status != 200:
                        yield event.plain_result("获取价格失败，API 服务暂时不可用。")
                        return
                    price_data = await resp.json()
                
                if coin_id not in price_data:
                    yield event.plain_result(f"无法获取 {name} ({symbol}) 的价格信息。")
                    return

                prices = price_data[coin_id]
                usd_price = prices.get("usd", "N/A")
                cny_price = prices.get("cny", "N/A")

                result_msg = (
                    f"💰 {name} ({symbol.upper()})\n"
                    f"💵 USD: ${usd_price}\n"
                    f"💴 CNY: ¥{cny_price}\n"
                    f"Powered by CoinGecko"
                )
                yield event.plain_result(result_msg)

        except Exception as e:
            logger.error(f"查询虚拟币出错: {e}")
            yield event.plain_result(f"查询出错: {str(e)}")
