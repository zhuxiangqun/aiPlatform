"""
CLI - Command Line Interface

命令行工具基类，基于 Click 构建。
"""

import click
from typing import Any, Callable, Optional
from datetime import datetime


class CLI:
    """命令行工具"""

    def __init__(self, name: str = "aiplat"):
        self.name = name
        self._commands: dict[str, click.Command] = {}
        self._app = click.Group(name=name)

    def command(self, name: str, help: str = "") -> click.Command:
        """装饰器：定义命令"""
        def decorator(func: Callable) -> click.Command:
            cmd = click.command(name=name, help=help)(func)
            self._commands[name] = cmd
            self._app.add_command(cmd)
            return cmd
        return decorator

    def group(self, name: str) -> click.Group:
        """装饰器：定义命令组"""
        grp = click.group(name=name)
        self._app.add_command(grp)
        return grp

    def add_command(self, cmd: click.Command) -> None:
        """添加命令"""
        self._commands[cmd.name] = cmd
        self._app.add_command(cmd)

    def run(self) -> None:
        """运行 CLI"""
        self._app()


@click.group()
@click.option("--api-key", "-k", help="API Key")
@click.option("--base-url", "-u", default="http://localhost:8080", help="API Base URL")
@click.pass_context
def aiplat(ctx, api_key: str, base_url: str):
    """aiPlat CLI - AI Platform Command Line Interface"""
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["base_url"] = base_url


@aiplat.command("agents")
def list_agents():
    """List available agents"""
    click.echo("Listing agents...")


@aiplat.command("execute")
@click.argument("agent")
@click.option("--input", "-i", help="Input message")
def execute_agent(agent: str, input: str):
    """Execute an agent"""
    click.echo(f"Executing agent: {agent}")


@aiplat.command("run")
@click.argument("skill")
@click.option("--param", "-p", multiple=True, help="Parameters")
def run_skill(skill: str, param: tuple):
    """Run a skill"""
    click.echo(f"Running skill: {skill}")


@aiplat.command("status")
def status():
    """Show system status"""
    click.echo("System: aiPlat")
    click.echo(f"Status: healthy")
    click.echo(f"Timestamp: {datetime.now()}")


def cli():
    """CLI 入口"""
    aiplat()


cli()