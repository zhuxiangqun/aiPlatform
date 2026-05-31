import unittest
from unittest.mock import MagicMock
from services.prd_generator import PRDGenerator
from services.conversation_service import ConversationService

class TestServices(unittest.TestCase):
    def test_prd_generator(self):
        db_mock = MagicMock()
        generator = PRDGenerator(db_mock)
        result = generator.generate_prd("proj-1", "Test message")
        self.assertIn("Test message", result)

    def test_conversation_service(self):
        db_mock = MagicMock()
        service = ConversationService(db_mock)
        db_mock.query.return_value.filter.return_value.first.return_value = MagicMock(name="TestProject")
        with self.assertRaises(ValueError):
            service.process_message("nonexistent", "Hello")

if __name__ == "__main__":
    unittest.main()