"""
Management Module Configuration
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class ManagementConfig:
    """Management module configuration"""
    
    # Module enable flags
    enabled: bool = True
    
    # Monitoring configuration
    monitoring_enabled: bool = True
    monitoring_interval: int = 10  # seconds
    health_check_enabled: bool = True
    health_check_interval: int = 60  # seconds
    
    # Alert configuration
    alert_enabled: bool = True
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'ManagementConfig':
        """Create config from dictionary"""
        management = config.get('management', {})
        return cls(
            enabled=management.get('enabled', True),
            monitoring_enabled=management.get('monitoring', {}).get('enabled', True),
            monitoring_interval=management.get('monitoring', {}).get('interval', 10),
            health_check_enabled=management.get('health_check', {}).get('enabled', True),
            health_check_interval=management.get('health_check', {}).get('interval', 60),
            alert_enabled=management.get('alerts', {}).get('enabled', True)
        )


class ManagementConfigLoader:
    """Configuration loader for management module"""
    
    @staticmethod
    def load(config_path: str = None) -> ManagementConfig:
        """
        Load configuration from file or use defaults.
        
        Args:
            config_path: Optional path to configuration file
        
        Returns:
            ManagementConfig instance
        """
        # Default configuration
        default_config = {
            'management': {
                'enabled': True,
                'monitoring': {
                    'enabled': True,
                    'interval': 10
                },
                'health_check': {
                    'enabled': True,
                    'interval': 60
                },
                'alerts': {
                    'enabled': True
                }
            }
        }
        
        if config_path:
            import json
            import logging
            import os
            import yaml as _yaml_module
            logger = logging.getLogger(__name__)
            try:
                if os.path.isfile(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        if config_path.endswith(('.yaml', '.yml')):
                            file_config = _yaml_module.safe_load(f) or {}
                        else:
                            file_config = json.load(f)
                    if isinstance(file_config, dict):
                        for key, value in file_config.items():
                            if hasattr(default_config, key):
                                setattr(default_config, key, value)
                    logger.info("Loaded management config from %s", config_path)
                else:
                    logger.warning("Config file not found: %s, using defaults", config_path)
            except Exception as e:
                logger.warning("Failed to load config from %s: %s. Using defaults.", config_path, e)
        
        return ManagementConfig.from_dict(default_config)