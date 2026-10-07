"""Plain-language clarify for object-store upload Tool/MCP creation.

Users should not be asked for endpoint URLs or env-var names.
Vendor answers map to SDK + conventional environment variables in the draft spec.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.apps.common.create_dialog_utils import trim_history

_UPLOAD_INTENT_RE = re.compile(
    r"对象存储|云存储|play_url|播放链接|oss|s3|minio|cos桶|上传视频|传到云|网盘|put_object",
    re.I,
)
_SKIP_CLOUD_RE = re.compile(
    r"不传到云|不要云|不用云|不上云|不需要云|不必上云|为什么要存到云|"
    r"只(留|存)在(本机|这台)|不需要播放|不要播放链接",
    re.I,
)
_VENDOR_RE = (
    (re.compile(r"腾讯|cos", re.I), "tencent"),
    (re.compile(r"亚马逊|amazon|\baws\b", re.I), "aws"),
    (re.compile(r"minio|自己(的|搭|建)|公司(自己|内网)|私有化", re.I), "minio"),
    (re.compile(r"阿里|aliyun|ali云", re.I), "aliyun"),
    (re.compile(r"还不确定|不确定|不知道|不清楚|随便|先按|默认", re.I), "aliyun"),
)
_LINK_PUBLIC_RE = re.compile(r"谁点开|都能播|公开|公有|直链|不需要登录", re.I)
_LINK_SIGNED_RE = re.compile(r"限时|签名|私有|不能公开|要过期", re.I)
_BUCKET_RE = re.compile(
    r"(?:桶(?:名叫|叫|名称是|是)?|bucket)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9._-]{1,62})",
    re.I,
)
_BARE_BUCKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$")
_NO_BUCKET_RE = re.compile(r"还没建|没有桶|不知道桶|未建|环境变量", re.I)

_VENDOR_SPEC = {
    "aliyun": {
        "label": "阿里云 OSS",
        "name": "oss_upload",
        "display_name": "阿里云视频上传",
        "sdk": "oss2.Bucket.put_object",
        "env": "OSS_ACCESS_KEY_ID、OSS_ACCESS_KEY_SECRET、OSS_BUCKET、OSS_ENDPOINT",
        "endpoint_fallback": "oss-cn-hangzhou.aliyuncs.com",
        "play_public": "https://{bucket}.{endpoint}/{key}",
    },
    "tencent": {
        "label": "腾讯云 COS",
        "name": "cos_upload",
        "display_name": "腾讯云视频上传",
        "sdk": "qcloud_cos CosS3Client.put_object 或等价 HTTP PUT",
        "env": "COS_SECRET_ID、COS_SECRET_KEY、COS_BUCKET、COS_REGION",
        "endpoint_fallback": "ap-guangzhou",
        "play_public": "https://{bucket}.cos.{region}.myqcloud.com/{key}",
    },
    "aws": {
        "label": "AWS S3",
        "name": "s3_upload",
        "display_name": "S3 视频上传",
        "sdk": "boto3 client.put_object",
        "env": "AWS_ACCESS_KEY_ID、AWS_SECRET_ACCESS_KEY、S3_BUCKET，可选 S3_ENDPOINT、S3_REGION",
        "endpoint_fallback": "s3.amazonaws.com",
        "play_public": "https://{bucket}.s3.amazonaws.com/{key}",
    },
    "minio": {
        "label": "MinIO",
        "name": "minio_upload",
        "display_name": "MinIO 视频上传",
        "sdk": "boto3 client.put_object（S3 协议）",
        "env": "MINIO_ENDPOINT、MINIO_ACCESS_KEY、MINIO_SECRET_KEY、MINIO_BUCKET",
        "endpoint_fallback": "http://127.0.0.1:9000",
        "play_public": "{MINIO_PUBLIC_BASE}/{key}",
    },
}

FRIENDLY_UPLOAD_QUESTIONS = [
    "别人要在网上点开播放吗？需要的话存在哪：阿里云 / 腾讯云 / 亚马逊 / 公司内网 / 还不确定。"
    "只在这台电脑用、不要网上链接：回复「不传到云上」。",
    "存储桶叫什么？控制台里那个英文名字即可。还没建过就回复「还没建」。",
    "上传后别人怎么打开？谁点开都能播 / 只有限时链接能播 / 还不确定",
]
SKIP_CLOUD_REPLY = (
    "可以不上云。只有别人要用浏览器打开播放链接时，才需要一块能上网的存储"
    "（阿里云、腾讯云或公司内网）。只在这台电脑处理、不要外链："
    "关掉本窗口，回到 Skill 点「改成只出文案」。不要用 localhost 假地址冒充播放链接。"
    "若确实要网上播放，再回复：阿里云 / 腾讯云 / 亚马逊 / 公司内网。"
)


def looks_like_upload_create(blob: str) -> bool:
    return bool(_UPLOAD_INTENT_RE.search(str(blob or "")))


def _user_answer_blob(history: List[Dict[str, str]], text: str) -> str:
    """User replies only; drop the canned seed so 'oss' does not count as 阿里云."""
    users = [str(m.get("content") or "") for m in history if m.get("role") == "user"]
    users.append(str(text or ""))
    kept: List[str] = []
    for u in users:
        if re.search(
            r"名称请含 oss|禁止假装成功|不要用浏览器或计算器|不要问 endpoint|不要先问 SSE|我不是技术人员",
            u,
        ):
            # still keep explicit vendor words if the user mixed them into the seed
            if not re.search(
                r"阿里|腾讯|亚马逊|amazon|\baws\b|minio|还不确定|不传到云",
                u,
                re.I,
            ):
                continue
        kept.append(u)
    return "\n".join(kept).strip()


def parse_upload_plain_facts(blob: str) -> Dict[str, Any]:
    text = str(blob or "").strip()
    vendor = None
    if _SKIP_CLOUD_RE.search(text):
        vendor = "skip_cloud"
    else:
        for rx, key in _VENDOR_RE:
            if rx.search(text):
                vendor = key
                break
    unsure = bool(re.search(r"还不确定|不确定|不知道|不清楚|随便|先按|默认", text))
    link = None
    if _LINK_SIGNED_RE.search(text):
        link = "signed"
    elif _LINK_PUBLIC_RE.search(text):
        link = "public"
    elif vendor and unsure:
        link = "public"
    bucket = None
    bucket_from_env = False
    if _NO_BUCKET_RE.search(text) or (vendor and unsure and not _BUCKET_RE.search(text)):
        bucket_from_env = True
        bucket = ""
    else:
        m = _BUCKET_RE.search(text)
        if m:
            bucket = m.group(1)
        else:
            for line in text.splitlines():
                s = line.strip().strip("0123456789.、）) ")
                if _BARE_BUCKET_RE.match(s) and not re.search(
                    r"阿里|腾讯|亚马逊|aws|minio|公开|限时", s, re.I
                ):
                    bucket = s
                    break
    return {
        "vendor": vendor,
        "link": link,
        "bucket": bucket,
        "bucket_from_env": bucket_from_env,
    }


def _missing_upload_fields(facts: Dict[str, Any]) -> List[str]:
    if facts.get("vendor") == "skip_cloud":
        return []
    qs: List[str] = []
    if not facts.get("vendor"):
        qs.append(FRIENDLY_UPLOAD_QUESTIONS[0])
    if not facts.get("bucket") and not facts.get("bucket_from_env"):
        qs.append(FRIENDLY_UPLOAD_QUESTIONS[1])
    if not facts.get("link"):
        qs.append(FRIENDLY_UPLOAD_QUESTIONS[2])
    return qs


def synthesize_upload_tool_description(facts: Dict[str, Any]) -> str:
    spec = _VENDOR_SPEC[str(facts.get("vendor") or "aliyun")]
    bucket = str(facts.get("bucket") or "").strip()
    bucket_line = (
        f"桶名固定为 {bucket}，同时允许环境变量覆盖。"
        if bucket
        else "桶名只从环境变量读取，未配置时 execute 必须 raise。"
    )
    if facts.get("link") == "signed":
        play = "play_url 用 SDK 生成限时签名 URL，禁止写死 localhost 或 example.com。"
    else:
        play = (
            f"play_url 按公有读拼接：{spec['play_public']}；"
            "也可用 OSS_PUBLIC_BASE / S3_PUBLIC_BASE / MINIO_PUBLIC_BASE 覆盖前缀。"
        )
    return (
        f"{spec['display_name']}。名称 {spec['name']}。"
        "入参 file_path（本地视频路径，必填）、object_key（可选）。"
        f"用 {spec['sdk']} 真实 PUT 上传。"
        f"凭据与连接只读环境变量：{spec['env']}。"
        f"{spec['label']} 未设 endpoint 时回退 {spec['endpoint_fallback']}。"
        f"{bucket_line}{play}"
        "缺密钥或桶名必须 raise，禁止假装成功或编造 play_url。"
    )


def maybe_upload_tool_clarify(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """If this turn is upload-tool creation, return ask/draft gate (skip jargon LLM)."""
    trimmed = trim_history(history)
    blob = "\n".join(
        [str(m.get("content") or "") for m in trimmed] + [str(text or "")]
    )
    if not looks_like_upload_create(blob):
        return None
    answers = _user_answer_blob(trimmed, text)
    facts = parse_upload_plain_facts(answers)
    if facts.get("vendor") == "skip_cloud":
        return {"next": "ask", "reply": SKIP_CLOUD_REPLY, "questions": []}
    missing = _missing_upload_fields(facts)
    if missing:
        return {
            "next": "ask",
            "reply": (
                "不是必须上公有云。只有需要网上播放链接时才要存到能打开的地方；"
                "只在本机用就回「不传到云上」。选云厂商时不用填网址和密钥名。"
            ),
            "questions": missing,
        }
    spec = _VENDOR_SPEC[str(facts.get("vendor") or "aliyun")]
    return {
        "next": "draft",
        "name": spec["name"],
        "display_name": spec["display_name"],
        "description": synthesize_upload_tool_description(facts),
        "facts": facts,
    }


def maybe_upload_mcp_clarify(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """Same plain questions for upload MCP; still need a real upload server later."""
    trimmed = trim_history(history)
    blob = "\n".join(
        [str(m.get("content") or "") for m in trimmed] + [str(text or "")]
    )
    if not looks_like_upload_create(blob):
        return None
    answers = _user_answer_blob(trimmed, text)
    facts = parse_upload_plain_facts(answers)
    if facts.get("vendor") == "skip_cloud":
        return {"next": "ask", "reply": SKIP_CLOUD_REPLY, "questions": []}
    missing = _missing_upload_fields(facts)
    if missing:
        return {
            "next": "ask",
            "reply": (
                "不是必须上公有云。需要网上播放才接存储；只在本机用回「不传到云上」。"
            ),
            "questions": missing,
        }
    spec = _VENDOR_SPEC[str(facts.get("vendor") or "aliyun")]
    desc = (
        f"对象存储上传 MCP（{spec['label']}）。名称含 oss 或 upload。"
        "allowed_tools 必须含 put_object 或 upload。"
        f"凭据走环境变量 {spec['env']}，禁止浏览器/计算器冒充。"
        + synthesize_upload_tool_description(facts)
    )
    return {
        "next": "draft",
        "name": spec["name"].replace("_upload", "_oss_mcp"),
        "display_name": spec["display_name"] + " MCP",
        "description": desc,
        "facts": facts,
    }
