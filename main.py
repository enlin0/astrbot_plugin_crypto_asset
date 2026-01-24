from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp
import asyncio
import os
import json
import time

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
        self.data_dir = os.path.join(os.getcwd(), 'data', 'astrbot_plugin_crypto_asset_data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.wallets_file = os.path.join(self.data_dir, 'wallets.json')
        
        # 加载钱包数据
        self.wallets = self.load_wallets()
        
        # 启动监控任务
        self.monitor_task = asyncio.create_task(self.monitor_loop())

    def load_wallets(self):
        if os.path.exists(self.wallets_file):
            try:
                with open(self.wallets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载钱包数据失败: {e}")
                return {}
        return {}

    def save_wallets(self):
        try:
            with open(self.wallets_file, 'w', encoding='utf-8') as f:
                json.dump(self.wallets, f, indent=4, ensure_ascii=False)
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
        logger.info("虚拟币转账监控任务已启动 (多链版)")
        while True:
            try:
                interval = self.config.get("check_interval", 60)
                
                async with aiohttp.ClientSession() as session:
                    for user_id, user_wallets in self.wallets.items():
                        for address, info in user_wallets.items():
                            chain = info.get("chain", "eth")
                            if chain not in self.chains:
                                continue
                            
                            # 获取对应链的 API Key
                            key_config_name = self.chains[chain]["key_config"]
                            api_key = self.config.get(key_config_name)
                            
                            if not api_key:
                                # 记录一次日志即可，避免刷屏，实际生产中可以优化
                                # logger.warning(f"未配置 {chain} 的 API Key")
                                continue

                            if chain == "tron":
                                await self.check_tron(session, user_id, address, info, api_key)
                            else:
                                await self.check_evm(session, user_id, address, info, api_key, chain)
                                
                            # 避免 API 速率限制
                            await asyncio.sleep(0.5)
                            
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(60)

    async def check_evm(self, session, user_id, address, info, api_key, chain):
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
                        # 过滤掉 value 为 0 的交易 (可选)
                        if int(tx["value"]) == 0:
                            new_last_block = max(new_last_block, int(tx["blockNumber"]))
                            continue
                            
                        await self.notify_user_evm(user_id, address, info.get("remark", ""), tx, chain)
                        new_last_block = max(new_last_block, int(tx["blockNumber"]))
                    
                    self.wallets[user_id][address]["last_block"] = new_last_block
                    self.save_wallets()
                    
        except Exception as e:
            logger.error(f"监控 EVM 地址 {address} ({chain}) 出错: {e}")

    async def check_tron(self, session, user_id, address, info, api_key):
        chain_conf = self.chains["tron"]
        # Tron 使用 timestamp 或 block_timestamp 记录
        # 我们这里存储 last_timestamp (毫秒)
        last_ts = info.get("last_timestamp", 0)
        
        # TronGrid API
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
                if resp.status != 200:
                    # logger.warning(f"Tron API Error: {resp.status}")
                    return
                
                data = await resp.json()
                
                if data.get("success") and data.get("data"):
                    txs = data["data"]
                    new_last_ts = last_ts
                    
                    for tx in txs:
                        block_ts = tx.get("block_timestamp", 0)
                        
                        # 解析 TRX 转账
                        raw_data = tx.get("raw_data", {})
                        contract = raw_data.get("contract", [])[0]
                        if contract.get("type") == "TransferContract":
                            value = contract["parameter"]["value"]["amount"]
                            await self.notify_user_tron(user_id, address, info.get("remark", ""), tx, value, "TRX")
                        
                        # 解析 TRC20 (USDT) - 需要调用 trc20 专用接口，或者解析 triggerSmartContract
                        # TronGrid 的 transactions 接口通常包含 TriggerSmartContract
                        # 但解析内部数据较复杂。简单起见，这里只处理 TRX 转账。
                        # 若要支持 USDT，需要请求 /accounts/{address}/transactions/trc20
                        
                        new_last_ts = max(new_last_ts, block_ts)
                    
                    self.wallets[user_id][address]["last_timestamp"] = new_last_ts
                    self.save_wallets()
            
            # 额外检查 TRC20 (主要是 USDT)
            await self.check_tron_trc20(session, user_id, address, info, api_key, last_ts)

        except Exception as e:
            logger.error(f"监控 Tron 地址 {address} 出错: {e}")

    async def check_tron_trc20(self, session, user_id, address, info, api_key, last_ts):
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
                    new_last_ts = self.wallets[user_id][address].get("last_timestamp", last_ts)
                    
                    for tx in txs:
                        block_ts = int(tx.get("block_timestamp", 0))
                        token_info = tx.get("token_info", {})
                        symbol = token_info.get("symbol", "Unknown")
                        decimals = int(token_info.get("decimals", 6))
                        value = int(tx.get("value", 0))
                        
                        real_value = value / (10 ** decimals)
                        
                        await self.notify_user_tron_trc20(user_id, address, info.get("remark", ""), tx, real_value, symbol)
                        
                        new_last_ts = max(new_last_ts, block_ts)
                        
                    self.wallets[user_id][address]["last_timestamp"] = new_last_ts
                    self.save_wallets()
                    
        except Exception as e:
            logger.error(f"监控 Tron TRC20 出错: {e}")

    async def notify_user_evm(self, user_id, address, remark, tx, chain):
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

    async def notify_user_tron(self, user_id, address, remark, tx, value, symbol):
        # TRX decimals = 6
        real_value = value / 10**6
        tx_id = tx["txID"]
        # raw_data.contract[0].parameter.value.ownerAddress 是 hex 格式，需要转 base58 比较麻烦
        # 这里简化，只通知有交易
        
        msg = (
            f"🔔 **Tron 转账提醒**\n"
            f"钱包: {remark} ({address[:6]}...)\n"
            f"交易金额: {real_value:.4f} {symbol}\n"
            f"交易哈希: {tx_id[:6]}...\n"
            f"[查看详情](https://tronscan.org/#/transaction/{tx_id})"
        )
        logger.info(f"Notify {user_id}: {msg}")

    async def notify_user_tron_trc20(self, user_id, address, remark, tx, value, symbol):
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
        if user_id not in self.wallets:
            self.wallets[user_id] = {}
            
        if address in self.wallets[user_id]:
            current_chain = self.wallets[user_id][address].get("chain", "eth")
            yield event.plain_result(f"该地址已在监控列表中 ({current_chain}): {address}")
            return

        # 自动推断链
        target_chain = "eth"
        if address.startswith("T"):
            target_chain = "tron"
        elif chain:
            target_chain = chain.lower()
        
        if target_chain not in self.chains:
            yield event.plain_result(f"不支持的链: {target_chain}。支持: {', '.join(self.chains.keys())}")
            return

        # 获取初始状态
        start_point = 0
        try:
            key_config = self.chains[target_chain]["key_config"]
            api_key = self.config.get(key_config)
            
            if not api_key:
                 yield event.plain_result(f"⚠️ 警告: 未配置 {target_chain} 的 API Key，监控可能无法工作。请联系管理员配置。")

            async with aiohttp.ClientSession() as session:
                if target_chain == "tron":
                    # Tron 使用 timestamp
                    start_point = int(time.time() * 1000)
                else:
                    # EVM 使用 blockNumber
                    if api_key:
                        url = self.chains[target_chain]["api_url"]
                        params = {"module": "proxy", "action": "eth_blockNumber", "apikey": api_key}
                        async with session.get(url, params=params) as resp:
                            if resp.status == 200:
                                d = await resp.json()
                                if "result" in d:
                                    start_point = int(d["result"], 16)
        except Exception as e:
            logger.warning(f"获取初始状态失败: {e}")
            
        self.wallets[user_id][address] = {
            "chain": target_chain,
            "remark": remark,
            "last_block": start_point if target_chain != "tron" else 0,
            "last_timestamp": start_point if target_chain == "tron" else 0
        }
        self.save_wallets()
        
        yield event.plain_result(f"✅ 已添加监控 ({self.chains[target_chain]['name']}):\n{remark}\n{address}")

    @filter.command("unwatch")
    async def unwatch_wallet(self, event: AstrMessageEvent, address: str):
        '''取消监控钱包。用法: /unwatch <地址>'''
        user_id = event.unified_msg_origin
        
        if user_id in self.wallets and address in self.wallets[user_id]:
            del self.wallets[user_id][address]
            self.save_wallets()
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

    # 保留原有的价格查询功能
    @filter.command("price")
    async def get_price(self, event: AstrMessageEvent, coin: str):
        '''查询虚拟币价格。用法: /price <币种名称或代码>'''
        if not coin:
            yield event.plain_result("请提供币种名称或代码，例如: /price BTC")
            return

        coin_name = coin.strip()
        
        try:
            async with aiohttp.ClientSession() as session:
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
