#!/usr/bin/env python3
"""
安装验证工具
================================================================

验证 sidecar 是否正确安装并运行。
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import aiohttp


async def verify_sidecar(base_url: str = "http://localhost:8765") -> bool:
    """验证 sidecar 是否可用"""
    print(f"检查 Sidecar: {base_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 1. 健康检查
            async with session.get(f"{base_url}/health", timeout=5) as resp:
                if resp.status != 200:
                    print(f"  ❌ 健康检查失败: HTTP {resp.status}")
                    return False
                data = await resp.json()
                print(f"  ✅ 健康检查通过")
                print(f"     状态: {data.get('status')}")
                print(f"     活跃卡片: {data.get('active_cards', 0)}")
            
            # 2. 测试事件发送
            test_event = {
                "schema_version": "1.0",
                "event": "message_received",
                "data": {
                    "chat_id": "test_verify",
                    "message_id": "test_msg",
                    "user_id": "test_user",
                    "greeting": "Testing...",
                    "model": "test",
                    "text": "This is a verification message",
                }
            }
            
            async with session.post(f"{base_url}/events", json=test_event, timeout=5) as resp:
                if resp.status != 200:
                    print(f"  ❌ 事件发送失败: HTTP {resp.status}")
                    return False
                result = await resp.json()
                print(f"  ✅ 事件发送成功")
                print(f"     响应: {result}")
        
        return True
        
    except aiohttp.ClientError as e:
        print(f"  ❌ 连接失败: {e}")
        return False
    except asyncio.TimeoutError:
        print(f"  ❌ 连接超时")
        return False


def verify_lark_cli() -> bool:
    """验证 lark-cli 是否可用"""
    import subprocess
    
    print("检查 lark-cli...")
    try:
        result = subprocess.run(
            ['lark-cli', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"  ✅ lark-cli 已安装")
            return True
        else:
            print(f"  ❌ lark-cli 错误: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  ❌ lark-cli 未找到（请运行: npm install -g @larksuite/oapi-cli）")
        return False
    except Exception as e:
        print(f"  ❌ 检查异常: {e}")
        return False


def verify_feishu_config(hermes_dir: Path) -> bool:
    """验证飞书配置"""
    print("检查飞书配置...")
    
    env_file = hermes_dir / '.env'
    if not env_file.exists():
        print(f"  ❌ .env 文件不存在: {env_file}")
        return False
    
    content = env_file.read_text()
    has_app_id = 'FEISHU_APP_ID=' in content and not content.startswith('#FEISHU_APP_ID=')
    has_app_secret = 'FEISHU_APP_SECRET=' in content
    
    if has_app_id and has_app_secret:
        print(f"  ✅ 飞书配置完整")
        return True
    else:
        print(f"  ❌ 缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
        return False


async def main():
    print("=" * 60)
    print("Feishu Streaming Card - 安装验证")
    print("=" * 60)
    print()
    
    hermes_dir = Path.home() / '.hermes'
    
    # 检查项
    checks = [
        ("lark-cli", verify_lark_cli()),
        ("飞书配置", verify_feishu_config(hermes_dir)),
    ]
    
    for name, result in checks:
        print(f"{name}: {'✅' if result else '❌'}")
    
    # 检查 sidecar 进程
    import subprocess
    print("\n检查 Sidecar 进程...")
    result = subprocess.run(
        ['ps', 'aux'],
        capture_output=True,
        text=True
    )
    sidecar_running = 'sidecar' in result.stdout.lower()
    print(f"  {'✅' if sidecar_running else '❌'} Sidecar 进程: {'运行中' if sidecar_running else '未运行'}")
    
    # 如果 sidecar 运行，测试 API
    if sidecar_running:
        print("\n测试 Sidecar API...")
        api_ok = await verify_sidecar()
        print(f"  {'✅' if api_ok else '❌'} API 响应")
    else:
        print("\n跳过 API 测试（Sidecar 未运行）")
        api_ok = False
    
    # 总结
    print()
    print("=" * 60)
    all_ok = all(r for _, r in checks) and api_ok
    if all_ok:
        print("✅ 所有检查通过，安装成功！")
        return 0
    else:
        print("❌ 部分检查失败，请查看上方错误信息")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
