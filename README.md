# 🪙 AstrBot 虚拟币资产查询与监控插件

<div align="center">

![AstrBot Plugin](https://img.shields.io/badge/AstrBot-Plugin-purple?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.2.0-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

</div>

`astrbot_plugin_crypto_asset` 是一个功能强大的 AstrBot 插件，专为加密货币用户设计。它不仅支持实时查询全网虚拟币价格，还具备多链钱包地址转账监控功能，让您随时随地掌握链上动态。

## ✨ 功能特性

- **📈 实时价格查询**: 支持查询 CoinGecko 收录的所有加密货币的实时价格（USD/CNY）。
- **👀 多链钱包监控**: 支持监控 Ethereum, Arbitrum, Optimism, Base, Tron 等主流区块链网络。
- **🔔 实时转账通知**: 当监控地址发生转账（转入/转出）时，立即发送详细通知，包含金额、对方地址及交易哈希。
- **💰 广泛的代币支持**:
  - **EVM 链**: 支持原生代币（如 ETH）监控。
  - **Tron 链**: 支持 TRX 及 TRC20 代币（如 USDT）监控。
- **👤 独立用户管理**: 每个用户可以独立添加和管理自己的监控列表，互不干扰。

## 🛠️ 安装方法

### 方法一：通过 AstrBot 插件市场安装（推荐）

1. 在 AstrBot 管理面板中搜索 `astrbot_plugin_crypto_asset`。
2. 点击安装即可。

### 方法二：手动安装

1. 进入 AstrBot 的插件目录 `data/plugins`。
2. 克隆本仓库：
   ```bash
   git clone https://github.com/AstrBotDevs/astrbot_plugin_crypto_asset.git
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. 重启 AstrBot。

## ⚙️ 配置说明

在 AstrBot 面板的插件配置中，您可以填入各条链的 API Key 以启用监控功能。建议配置以获得更稳定和快速的数据更新。

| 配置项 | 说明 | 默认值 | 获取方式 |
| :--- | :--- | :--- | :--- |
| `etherscan_api_key` | Ethereum 主网 API Key | (空) | [Etherscan](https://etherscan.io/myapikey) |
| `arbiscan_api_key` | Arbitrum API Key | (空) | [Arbiscan](https://arbiscan.io/myapikey) |
| `optimism_api_key` | Optimism API Key | (空) | [Optimistic Etherscan](https://optimistic.etherscan.io/myapikey) |
| `basescan_api_key` | Base API Key | (空) | [Basescan](https://basescan.org/myapikey) |
| `trongrid_api_key` | TronGrid API Key (Tron) | (空) | [TronGrid](https://www.trongrid.io/) |
| `check_interval` | 监控检查间隔（秒） | 60 | - |

> ⚠️ **注意**: 虽然不配置 API Key 也可以运行，但可能会因为公共 API 的速率限制导致监控不稳定或延迟。强烈建议申请免费的 API Key 进行配置。

## 📖 使用指南

### 1. 查询价格

查询任意虚拟币的当前价格。

- **指令**: `/price <币种名称或代码>`
- **示例**: 
  - `/price BTC`
  - `/price Ethereum`
  - `/price DOGE`

### 2. 监控钱包

添加一个钱包地址到监控列表。

- **指令**: `/watch <地址> [备注] [链类型]`
- **参数**:
  - `<地址>`: 钱包地址（0x... 或 T...）
  - `[备注]`: (可选) 给钱包起的别名，方便识别
  - `[链类型]`: (可选) 指定链类型，支持 `eth`, `arb`, `op`, `base`, `tron`。
    - 如果地址以 `T` 开头，会自动识别为 `tron`。
    - 如果未指定且以 `0x` 开头，默认为 `eth`。
- **示例**:
  - 监控 ETH 钱包: `/watch 0x1234...5678 我的主钱包`
  - 监控 Tron 钱包: `/watch TAbc...1234 TRC20收币`
  - 监控 Arb 钱包: `/watch 0x1234...5678 Arb交互 arb`

### 3. 查看监控列表

查看当前用户所有正在监控的钱包。

- **指令**: `/wallets`

### 4. 取消监控

从监控列表中移除某个钱包。

- **指令**: `/unwatch <地址>`
- **示例**: `/unwatch 0x1234...5678`

## 🔗 支持的区块链

| 标识符 (`chain`) | 网络名称 | 浏览器 | 原生代币 |
| :--- | :--- | :--- | :--- |
| `eth` | Ethereum | [Etherscan](https://etherscan.io) | ETH |
| `arb` | Arbitrum | [Arbiscan](https://arbiscan.io) | ETH |
| `op` | Optimism | [Optimism Etherscan](https://optimistic.etherscan.io) | ETH |
| `base` | Base | [Basescan](https://basescan.org) | ETH |
| `tron` | Tron | [TronScan](https://tronscan.org) | TRX |

## 📝 待办事项 / 计划

- [ ] 支持更多 EVM 兼容链 (如 BSC, Polygon 等)。
- [ ] 支持 Solana 链监控。
- [ ] 增加价格预警功能。
- [ ] 支持 NFT 交易监控。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进此插件！

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。
