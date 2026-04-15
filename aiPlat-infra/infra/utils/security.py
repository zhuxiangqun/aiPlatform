"""
Security Utils - 安全工具

文档位置：docs/utils/index.md
"""

import hashlib
import secrets
import base64
from typing import Optional

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class SecurityUtils:
    """
    安全工具实现

    支持：
    - 哈希计算
    - 加密/解密
    - 令牌生成
    - 签名验证
    """

    def __init__(self, secret_key: Optional[str] = None):
        self._secret_key = secret_key
        self._fernet = None
        if HAS_CRYPTO and secret_key:
            self._fernet = Fernet(self._derive_key(secret_key))

    def hash(self, data: str, algorithm: str = "sha256") -> str:
        """哈希计算"""
        if algorithm == "sha256":
            return hashlib.sha256(data.encode()).hexdigest()
        elif algorithm == "sha512":
            return hashlib.sha512(data.encode()).hexdigest()
        elif algorithm == "md5":
            return hashlib.md5(data.encode()).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def encrypt(self, data: str) -> str:
        """加密"""
        if not self._fernet:
            raise ValueError("Encryption not available. Set secret_key.")

        encrypted = self._fernet.encrypt(data.encode())
        return base64.b64encode(encrypted).decode()

    def decrypt(self, data: str) -> str:
        """解密"""
        if not self._fernet:
            raise ValueError("Decryption not available. Set secret_key.")

        decoded = base64.b64decode(data.encode())
        decrypted = self._fernet.decrypt(decoded)
        return decrypted.decode()

    def generate_token(self, length: int = 32) -> str:
        """生成安全令牌"""
        return secrets.token_urlsafe(length)

    def generate_password(self, length: int = 16) -> str:
        """生成随机密码"""
        alphabet = (
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        )
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def verify_signature(self, data: str, signature: str) -> bool:
        """验证签名（简化版）"""
        expected = self.hash(data)
        return secrets.compare_digest(expected, signature)

    def _derive_key(self, password: str) -> bytes:
        """从密码派生密钥"""
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"ai-platform-salt",
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))
