#!/usr/bin/env python3
"""
Hermes 版本检测工具
================================================================

检测 Hermes 安装状态、版本、以及流式卡片安装状态。
用于 installer 决定使用哪种 patch 策略。
"""

from __future__ import annotations

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Hermes 根目录默认位置
DEFAULT_HERMES_DIR = Path.home() / '.hermes'


def detect_hermes_version(hermes_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    检测 Hermes 版本和流式卡片安装状态。
    
    Returns:
        检测结果字典：
        {
            "hermes_dir": str,
            "version": str,
            "commit": str,
            "is_compatible": bool,
            "streaming_installed": bool,
            "installed_mode": "legacy" | "sidecar" | "none",
            "injected_files": List[str],
            "backups_available": int,
            "gateway_healthy": bool,
        }
    """
    if hermes_dir is None:
        hermes_dir = DEFAULT_HERMES_DIR
    
    hermes_dir = Path(hermes_dir)
    result = {
        'hermes_dir': str(hermes_dir),
        'version': 'unknown',
        'commit': 'unknown',
        'is_compatible': False,
        'streaming_installed': False,
        'installed_mode': 'none',
        'injected_files': [],
        'backups_available': 0,
        'gateway_healthy': False,
        'errors': [],
    }
    
    # 1. 检查目录结构
    if not hermes_dir.exists():
        result['errors'].append(f"Hermes directory not found: {hermes_dir}")
        return result
    
    # 2. 检查 gateway 可执行文件
    gateway_script = hermes_dir / 'hermes-agent' / 'hermes_cli' / 'main.py'
    if not gateway_script.exists():
        result['errors'].append("Gateway main.py not found")
        return result
    
    # 3. 尝试获取版本信息
    version_file = hermes_dir / 'VERSION'
    if version_file.exists():
        result['version'] = version_file.read_text().strip()
    else:
        # 从 git 获取
        import subprocess
        try:
            git_dir = hermes_dir / '.git'
            if git_dir.exists():
                commit = subprocess.run(
                    ['git', '--git-dir', str(git_dir), 'rev-parse', '--short', 'HEAD'],
                    capture_output=True, text=True
                ).stdout.strip()
                result['commit'] = commit
        except Exception:
            pass
    
    # 4. 检测流式卡片安装状态
    feishu_file = hermes_dir / 'gateway' / 'platforms' / 'feishu.py'
    run_file = hermes_dir / 'gateway' / 'run.py'
    
    if feishu_file.exists():
        content = feishu_file.read_text()
        
        # 检查是否有 streaming card 注入代码
        if 'Feishu Streaming Card' in content or 'streaming_card' in content:
            result['streaming_installed'] = True
            result['installed_mode'] = 'legacy'
            
            # 判断版本兼容性
            if 'StreamingAdapter' in content or 'sidecar' in content.lower():
                result['installed_mode'] = 'sidecar'
                result['is_compatible'] = True
            else:
                # legacy 模式，检查版本匹配
                result['is_compatible'] = _check_legacy_compatibility(content)
    
    # 5. 检查备份
    backup_dir = hermes_dir / '.fsc_backups'
    if backup_dir.exists():
        backups = list(backup_dir.iterdir())
        result['backups_available'] = len(backups)
    
    # 6. 检查 gateway 进程健康状态
    import subprocess
    try:
        pid_file = hermes_dir / 'gateway.pid'
        if pid_file.exists():
            pid = json.loads(pid_file.read_text()).get('pid')
            if pid:
                # 检查进程是否存在
                proc = subprocess.run(
                    ['ps', '-p', str(pid)], 
                    capture_output=True
                )
                result['gateway_healthy'] = proc.returncode == 0
    except Exception:
        pass
    
    return result


def _check_legacy_compatibility(feishu_content: str) -> bool:
    """
    检查 legacy 注入代码与当前 Hermes 版本的兼容性。
    
    简单启发式检测：
      - 检查关键方法是否存在
      - 检查缩进模式是否匹配
    """
    checks = [
        ('send_streaming_card', 'send_streaming_card 方法'),
        ('_update_card_element', '_update_card_element 方法'),
        ('finalize_streaming_card', 'finalize_streaming_card 方法'),
        ('_streaming_card_locks', '_streaming_card_locks 属性'),
    ]
    
    missing = []
    for keyword, desc in checks:
        if keyword not in feishu_content:
            missing.append(desc)
    
    if missing:
        logger.warning(f"Legacy mode missing: {', '.join(missing)}")
        return False
    
    return True


def print_status(result: Dict[str, Any]) -> None:
    """打印检测结果（人类可读）"""
    print("=" * 60)
    print("Hermes Feishu Streaming Card - 检测报告")
    print("=" * 60)
    print(f"\nHermes 目录: {result['hermes_dir']}")
    print(f"版本: {result['version']} (commit: {result['commit']})")
    print(f"Gateway 状态: {'✅ 运行中' if result['gateway_healthy'] else '❌ 未运行'}")
    print()
    
    if result['streaming_installed']:
        print(f"流式卡片: ✅ 已安装")
        print(f"运行模式: {result['installed_mode']}")
        print(f"兼容性: {'✅ 兼容' if result['is_compatible'] else '⚠️  可能需要修复'}")
        print(f"可用备份: {result['backups_available']} 份")
    else:
        print("流式卡片: ❌ 未安装")
    
    if result['errors']:
        print("\n错误:")
        for err in result['errors']:
            print(f"  ❌ {err}")
    
    print()
    
    # 建议
    if not result['streaming_installed']:
        print("建议: 运行 installer.py 进行安装")
    elif result['installed_mode'] == 'legacy' and not result['is_compatible']:
        print("建议: 升级到 sidecar 模式（更安全）")
        print("  执行: python installer.py --upgrade")
    elif result['installed_mode'] == 'legacy' and result['is_compatible']:
        print("建议: 考虑升级到 sidecar 模式（一键回滚）")
        print("  执行: python installer.py --install-sidecar")
    else:
        print("状态: 运行正常")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = detect_hermes_version()
    print_status(result)
    
    # 退出码：0=正常, 1=未安装, 2=错误, 3=不兼容
    if result['errors']:
        sys.exit(2)
    if result['streaming_installed'] and not result['is_compatible']:
        sys.exit(3)
    sys.exit(0 if result['streaming_installed'] else 1)
