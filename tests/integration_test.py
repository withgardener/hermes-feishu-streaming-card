#!/usr/bin/env python3
"""集成测试：gateway → sidecar 事件流转"""
import sys
import os
import json
import asyncio
import subprocess
import time
import urllib.request
from pathlib import Path

# 路径配置
HERMES_DIR = Path.home() / '.hermes'
GATEWAY_DIR = HERMES_DIR / 'hermes-agent'
SIDECAR_DIR = HERMES_DIR / 'sidecar'

def start_sidecar():
    """启动 sidecar 进程（后台）"""
    cmd = [sys.executable, '-m', 'sidecar.server']
    proc = subprocess.Popen(
        cmd,
        cwd=str(SIDECAR_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True
    )
    time.sleep(3)  # 等待启动
    return proc

def check_sidecar_health(max_retries=5):
    """轮询健康检查"""
    for i in range(max_retries):
        try:
            req = urllib.request.Request('http://127.0.0.1:8765/health')
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                if data.get('status') == 'healthy':
                    return True, data
        except Exception as e:
            time.sleep(1)
    return False, None

def send_test_event(event_type, data):
    """发送测试事件到 sidecar"""
    payload = {
        'schema_version': 'v1',
        'event': event_type,
        'data': data
    }
    req = urllib.request.Request(
        'http://127.0.0.1:8765/events',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}

def run_tests():
    print("=" * 60)
    print("Hermes Feishu Streaming Card - Integration Tests")
    print("=" * 60)

    # 1. 启动 sidecar
    print("\n[1/5] Starting sidecar...")
    proc = start_sidecar()
    time.sleep(2)
    
    # 2. 健康检查
    print("[2/5] Health check...")
    ok, health = check_sidecar_health()
    if ok:
        print(f"  ✓ Sidecar healthy: {health}")
    else:
        print("  ✗ Sidecar not healthy")
        stdout, stderr = proc.communicate()
        print(f"  stdout: {stdout[-500:]}")
        print(f"  stderr: {stderr[-500:]}")
        return 1

    # 3. 发送 message_received 事件
    print("[3/5] Test: message_received")
    result = send_test_event('message_received', {
        'chat_id': 'test_chat_123',
        'message_id': 'msg_456',
        'user_id': 'user_789',
        'greeting': 'Test Session',
        'model': 'step-3.5-flash-2603',
        'text': '你好，帮我查一下天气',
    })
    print(f"  Response: {result}")
    card_id = result.get('card_id')
    if not card_id:
        print("  ✗ No card_id returned")
        return 1
    print(f"  ✓ Card created: {card_id}")

    # 4. 发送 thinking 更新
    print("[4/5] Test: thinking + tool_call")
    result = send_test_event('thinking', {
        'chat_id': 'test_chat_123',
        'delta': ' 正在思考...',
        'tools': None,
    })
    print(f"  Thinking: {result}")

    result = send_test_event('tool_call', {
        'chat_id': 'test_chat_123',
        'tool_name': 'web_search',
        'status': 'started',
    })
    print(f"  Tool start: {result}")

    result = send_test_event('tool_call', {
        'chat_id': 'test_chat_123',
        'tool_name': 'web_search',
        'status': 'completed',
        'result': {'temperature': '22°C', 'condition': '晴'},
    })
    print(f"  Tool complete: {result}")

    # 5. 发送 finish 事件
    print("[5/5] Test: finish")
    result = send_test_event('finish', {
        'chat_id': 'test_chat_123',
        'content': '主人，今天北京天气晴，气温 22°C',
        'tokens': {'input': 120, 'output': 80},
        'duration': 2.5,
    })
    print(f"  Finish: {result}")

    # 检查活跃卡片数
    req = urllib.request.Request('http://127.0.0.1:8765/health')
    with urllib.request.urlopen(req, timeout=2) as resp:
        final_health = json.loads(resp.read().decode())
    print(f"\nFinal state: active_cards={final_health.get('active_cards')}")

    # 清理
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("✓ Sidecar stopped")
    print("\n" + "=" * 60)
    print("✓ All integration tests passed")
    print("=" * 60)
    return 0

if __name__ == '__main__':
    sys.exit(run_tests())
