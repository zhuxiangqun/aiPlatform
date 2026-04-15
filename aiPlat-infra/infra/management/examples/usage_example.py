"""
Management Module Usage Examples

This file demonstrates how to use the management module.
"""

import asyncio
from infra.management import InfraManager
from infra.management.resources import ResourcesManager
from infra.management.llm import LLMManager
from infra.management.database import DatabaseManager


async def main():
    """Main example"""
    
    # 1. Create infrastructure manager
    infra_manager = InfraManager()
    
    # 2. Create and register managers
    resources_config = {
        "resources": {
            "gpu": {
                "provider": "nvidia",
                "default_quota": 1,
                "max_quota": 4
            }
        }
    }
    resources_manager = ResourcesManager(resources_config)
    infra_manager.register("resources", resources_manager)
    
    llm_config = {
        "llm": {
            "provider": "openai",
            "models": [
                {"name": "gpt-4", "provider": "openai", "priority": 100}
            ],
            "cost_tracking": {
                "enabled": True,
                "budget": {
                    "daily_limit": 100,
                    "monthly_limit": 3000
                }
            }
        }
    }
    llm_manager = LLMManager(llm_config)
    infra_manager.register("llm", llm_manager)
    
    db_config = {
        "database": {
            "postgres": {
                "host": "localhost",
                "port": 5432
            }
        }
    }
    db_manager = DatabaseManager(db_config)
    infra_manager.register("database", db_manager)
    
    # 3. Get all module status
    print("=== Module Status ===")
    all_status = await infra_manager.get_all_status()
    for name, status in all_status.items():
        print(f"{name}: {status.value}")
    
    # 4. Health check all modules
    print("\n=== Health Check ===")
    health_results = await infra_manager.health_check_all()
    for name, health in health_results.items():
        print(f"{name}: {health.status.value} - {health.message}")
    
    # 5. Get all metrics
    print("\n=== Metrics ===")
    all_metrics = await infra_manager.get_all_metrics()
    for name, metrics in all_metrics.items():
        print(f"\n{name}:")
        for metric in metrics[:3]:  # Show first 3 metrics
            print(f"  - {metric.name}: {metric.value} {metric.unit}")
    
    # 6. Diagnose all modules
    print("\n=== Diagnosis ===")
    diagnosis_results = await infra_manager.diagnose_all()
    for name, diagnosis in diagnosis_results.items():
        print(f"\n{name}:")
        print(f"  Healthy: {diagnosis['healthy']}")
        if diagnosis['issues']:
            print(f"  Issues: {diagnosis['issues']}")
        if diagnosis['recommendations']:
            print(f"  Recommendations: {diagnosis['recommendations']}")
    
    # 7. Use specific manager
    print("\n=== Resources Manager ===")
    resources = infra_manager.get("resources")
    
    # Allocate resources
    allocation = await resources.allocate({
        "resource_type": "gpu",
        "amount": 2
    })
    print(f"Allocated: {allocation.allocation_id}")
    
    # Get stats
    stats = await resources.get_stats()
    print(f"Total: {stats.total}, Used: {stats.used}, Available: {stats.available}")
    
    # Release resources
    await resources.release(allocation.allocation_id)
    print("Resources released")
    
    # 8. Use LLM manager
    print("\n=== LLM Manager ===")
    llm = infra_manager.get("llm")
    
    # Get cost
    cost = await llm.get_cost(period="daily")
    print(f"Daily cost: ${cost.total:.2f}")
    print(f"By model: {cost.by_model}")
    
    # Get budget status
    budget = await llm.get_budget_status()
    print(f"Daily budget: {budget.daily_percentage*100:.1f}% used")
    print(f"Monthly budget: {budget.monthly_percentage*100:.1f}% used")


if __name__ == "__main__":
    asyncio.run(main())