cd /d "D:\newassign\fintech-chatbot\backend"
.\.venv\Scripts\python.exe -c "import unittest, sys; suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_chatbot'); result = unittest.TextTestRunner(verbosity=1).run(suite); print('RESULT', result.wasSuccessful()); sys.exit(0 if result.wasSuccessful() else 1)"
