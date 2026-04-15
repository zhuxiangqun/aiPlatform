#!/usr/bin/env python3
"""
测试运行脚本 - 提供便捷的测试命令
"""

import subprocess
import sys
import os


def run_command(cmd: str, description: str):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    print(f"命令: {cmd}\n")
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode != 0:
        print(f"\n❌ {description} 失败")
        return False
    else:
        print(f"\n✅ {description} 成功")
        return True


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════╗
║          AI Platform - 数据库测试运行器                    ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # 切换到正确的目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("请选择要运行的测试:")
    print("1. 单元测试（快速，不需要Docker）")
    print("2. 集成测试（需要Docker）")
    print("3. 所有测试")
    print("4. PostgreSQL集成测试")
    print("5. MySQL集成测试")
    print("6. MongoDB集成测试")
    print("0. 退出")
    
    choice = input("\n请输入选项 (0-6): ").strip()
    
    if choice == "1":
        # 单元测试
        cmd = "pytest test_client.py -v --tb=short"
        run_command(cmd, "单元测试")
        
    elif choice == "2":
        # 集成测试
        print("\n⚠️  集成测试需要Docker运行中")
        print("请确保运行: docker ps")
        
        proceed = input("\n是否继续? (y/n): ").strip().lower()
        if proceed == 'y':
            cmd = "pytest test_integration.py -v --tb=short -s"
            run_command(cmd, "集成测试")
        else:
            print("已取消")
            
    elif choice == "3":
        # 所有测试
        cmd = "pytest . -v --tb=short"
        run_command(cmd, "所有测试")
        
    elif choice == "4":
        # PostgreSQL集成测试
        print("\n⚠️  集成测试需要Docker运行中")
        
        proceed = input("\n是否继续? (y/n): ").strip().lower()
        if proceed == 'y':
            cmd = "pytest test_integration.py::TestPostgreSQLIntegration -v --tb=short -s"
            run_command(cmd, "PostgreSQL集成测试")
        
    elif choice == "5":
        # MySQL集成测试
        print("\n⚠️  集成测试需要Docker运行中")
        
        proceed = input("\n是否继续? (y/n): ").strip().lower()
        if proceed == 'y':
            cmd = "pytest test_integration.py::TestMySQLIntegration -v --tb=short -s"
            run_command(cmd, "MySQL集成测试")
            
    elif choice == "6":
        # MongoDB集成测试
        print("\n⚠️  集成测试需要Docker运行中")
        
        proceed = input("\n是否继续? (y/n): ").strip().lower()
        if proceed == 'y':
            cmd = "pytest test_integration.py::TestMongoDBIntegration -v --tb=short -s"
            run_command(cmd, "MongoDB集成测试")
            
    elif choice == "0":
        print("\n退出测试运行器")
        sys.exit(0)
        
    else:
        print("\n❌ 无效的选项")
        sys.exit(1)


if __name__ == "__main__":
    main()