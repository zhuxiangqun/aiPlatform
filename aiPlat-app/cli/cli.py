"""
CLI - Command Line Interface

命令行工具基类，基于 Click 构建。
"""

import click
from typing import Any, Callable, Optional
from datetime import datetime

from services.kb import get_kb_service


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


@aiplat.group("kb")
def kb_group():
    """Knowledge Base commands"""
    pass


@kb_group.command("ingest")
@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--collection-id", default="default", help="Collection ID")
@click.option("--file", "file_path", required=True, help="PDF file path")
@click.pass_context
def kb_ingest(ctx, tenant_id: str, collection_id: str, file_path: str):
    """Upload and ingest a PDF into KB"""
    base_url = ctx.obj.get("base_url")
    api_key = ctx.obj.get("api_key") or ""
    svc = get_kb_service(base_url=base_url, api_key=api_key, tenant_id=tenant_id)
    resp = svc.upload_and_ingest_pdf(collection_id=collection_id, file_path=file_path)
    click.echo(resp)


@kb_group.command("query")
@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--collection-id", default="default", help="Collection ID")
@click.option("--question", "-q", required=True, help="Question text")
@click.option("--year", type=int, default=2026, help="Year")
@click.option("--out-dir", default="./kb_out", help="Output directory (save json/images/html)")
@click.pass_context
def kb_query(ctx, tenant_id: str, collection_id: str, question: str, year: int, out_dir: str):
    """Query KB and save an HTML report with bbox highlights"""
    import json
    from pathlib import Path

    base_url = ctx.obj.get("base_url")
    api_key = ctx.obj.get("api_key") or ""
    svc = get_kb_service(base_url=base_url, api_key=api_key, tenant_id=tenant_id)
    resp = svc.query(collection_id=collection_id, question=question, year=year, limit=50)

    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    (outp / "kb_query.json").write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

    # Download citation images and annotate response with local paths for the HTML report.
    kb = resp.get("kb") if isinstance(resp.get("kb"), dict) else {}
    cits = kb.get("citations") if isinstance(kb.get("citations"), list) else []
    for i, c in enumerate(cits):
        if not isinstance(c, dict):
            continue
        asset_url = c.get("asset_url")
        if not asset_url:
            continue
        try:
            local = svc.download_asset(asset_url=asset_url, out_path=str(outp / f"citation_{i+1:02d}.png"))
            c["local_asset"] = Path(local).name  # relative path for HTML
        except Exception as e:
            c["download_error"] = str(e)

    report_path = svc.write_html_report(kb_result=resp, out_dir=str(outp))
    click.echo(f"Saved: {outp / 'kb_query.json'}")
    click.echo(f"Saved: {report_path}")


def cli():
    """CLI 入口"""
    aiplat()


cli()
