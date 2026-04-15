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
            # TODO: Load from YAML/JSON file
            pass
        
        return ManagementConfig.from_dict(default_config)