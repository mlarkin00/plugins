import unittest
import sys
import os
import json
import io
from unittest.mock import patch, call, ANY

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMMY_TRANSCRIPT = os.path.join(BASE_DIR, 'tests', 'dummy_upload_session.jsonl')


class TestUploadSession(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(DUMMY_TRANSCRIPT):
            os.remove(DUMMY_TRANSCRIPT)
        sys.modules.pop('upload_session', None)

    def test_build_event_maps_user_role(self):
        import upload_session
        event = upload_session.build_event("user", "Hello there")
        self.assertEqual(event["author"], "user")
        self.assertEqual(event["content"]["role"], "user")
        self.assertEqual(event["content"]["parts"][0]["text"], "Hello there")

    def test_build_event_maps_assistant_to_agent_model(self):
        import upload_session
        event = upload_session.build_event("assistant", "Hi back")
        self.assertEqual(event["author"], "agent")
        self.assertEqual(event["content"]["role"], "model")
        self.assertEqual(event["content"]["parts"][0]["text"], "Hi back")

    def test_build_event_includes_optional_fields(self):
        import upload_session
        event = upload_session.build_event(
            "user", "With metadata",
            timestamp="2026-08-20T12:00:00Z",
            invocation_id="msg_001"
        )
        self.assertEqual(event["timestamp"], "2026-08-20T12:00:00Z")
        self.assertEqual(event["invocationId"], "msg_001")

    def test_build_event_omits_optional_fields_when_none(self):
        import upload_session
        event = upload_session.build_event("user", "No metadata")
        self.assertNotIn("timestamp", event)
        self.assertNotIn("invocationId", event)

    @patch('upload_session.create_session')
    @patch('upload_session.append_event')
    @patch('upload_session.get_access_token', return_value="fake-token")
    @patch('upload_session.get_plugin_config')
    @patch('upload_session.resolve_user_id', return_value="sha256:abc")
    def test_run_creates_session_and_appends_events(
        self, mock_user, mock_config, mock_token, mock_append, mock_create
    ):
        mock_config.return_value = {
            "project": "test-project",
            "location": "us-west1",
            "reasoning_engine_id": "eng-123"
        }
        mock_append.return_value = {"done": True}

        with open(DUMMY_TRANSCRIPT, 'w') as f:
            f.write(json.dumps({"role": "user", "content": "What is 2+2?"}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": "It is 4."}) + "\n")

        stdin = json.dumps({
            "sessionId": "ses_test123",
            "transcriptPath": DUMMY_TRANSCRIPT,
            "workspace": "/tmp"
        })
        with patch('sys.stdin', io.StringIO(stdin)):
            import upload_session
            upload_session.run()

        self.assertTrue(mock_create.called)
        mock_create.assert_called_once_with(
            ANY, "test-project", "fake-token",
            "ses_test123", "sha256:abc", "global"
        )
        self.assertEqual(mock_append.call_count, 2)
        first_event = mock_append.call_args_list[0][0][4]
        self.assertEqual(first_event["author"], "user")
        self.assertEqual(first_event["content"]["role"], "user")
        second_event = mock_append.call_args_list[1][0][4]
        self.assertEqual(second_event["author"], "agent")
        self.assertEqual(second_event["content"]["role"], "model")

    @patch('upload_session.create_session')
    @patch('upload_session.append_event')
    @patch('upload_session.get_access_token', return_value="fake-token")
    @patch('upload_session.get_plugin_config')
    @patch('upload_session.resolve_user_id', return_value="sha256:abc")
    def test_run_scope_is_global_regardless_of_workspace(
        self, mock_user, mock_config, mock_token, mock_append, mock_create
    ):
        mock_config.return_value = {
            "project": "test-project",
            "location": "us-west1",
            "reasoning_engine_id": "eng-123"
        }
        mock_append.return_value = {"done": True}

        with open(DUMMY_TRANSCRIPT, 'w') as f:
            f.write(json.dumps({"role": "user", "content": "scope check"}) + "\n")

        stdin = json.dumps({
            "sessionId": "ses_test456",
            "transcriptPath": DUMMY_TRANSCRIPT,
            "workspace": "/some/git/project"
        })
        with patch('sys.stdin', io.StringIO(stdin)):
            import upload_session
            upload_session.run()

        self.assertEqual(mock_create.call_args[0][5], "global")

    @patch('upload_session.create_session')
    @patch('upload_session.append_event')
    @patch('upload_session.get_access_token')
    def test_missing_transcript_does_not_call_api(self, mock_token, mock_append, mock_create):
        mock_token.return_value = "fake-token"
        stdin = json.dumps({
            "sessionId": "ses_test789",
            "transcriptPath": "/nonexistent/path.jsonl",
            "workspace": "/tmp"
        })
        with patch('sys.stdin', io.StringIO(stdin)):
            import upload_session
            upload_session.run()

        self.assertFalse(mock_create.called)
        self.assertFalse(mock_append.called)

    @patch('upload_session.create_session')
    @patch('upload_session.append_event')
    @patch('upload_session.get_access_token', return_value="fake-token")
    @patch('upload_session.get_plugin_config')
    @patch('upload_session.resolve_user_id', return_value="sha256:abc")
    def test_skips_turns_with_empty_content(
        self, mock_user, mock_config, mock_token, mock_append, mock_create
    ):
        mock_config.return_value = {
            "project": "test-project",
            "location": "us-west1",
            "reasoning_engine_id": "eng-123"
        }
        mock_append.return_value = {"done": True}

        with open(DUMMY_TRANSCRIPT, 'w') as f:
            f.write(json.dumps({"role": "user", "content": "real message"}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": ""}) + "\n")
            f.write(json.dumps({"role": "user", "content": "another real one"}) + "\n")

        stdin = json.dumps({
            "sessionId": "ses_test000",
            "transcriptPath": DUMMY_TRANSCRIPT,
            "workspace": "/tmp"
        })
        with patch('sys.stdin', io.StringIO(stdin)):
            import upload_session
            upload_session.run()

        self.assertEqual(mock_append.call_count, 2)

    @patch('upload_session.create_session')
    @patch('upload_session.append_event')
    @patch('upload_session.get_access_token', return_value="")
    def test_no_token_does_not_call_api(self, mock_token, mock_append, mock_create):
        stdin = json.dumps({
            "sessionId": "ses_test_noauth",
            "transcriptPath": DUMMY_TRANSCRIPT,
            "workspace": "/tmp"
        })
        with patch('sys.stdin', io.StringIO(stdin)):
            import upload_session
            upload_session.run()

        self.assertFalse(mock_create.called)
        self.assertFalse(mock_append.called)


if __name__ == '__main__':
    unittest.main()
