import unittest
from unittest.mock import MagicMock, patch

import main
from services.sms_templates import SMS_TEMPLATES, personalize_sms


class SmsTemplateTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(main.app.config, TESTING=True)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.client = main.app.test_client()
        self.admin = {'id': 101, 'name': 'Admin', 'username': 'admin',
                      'is_active': 1, 'is_admin': 1, 'is_standby': 0}
        self.coaches = [
            {'id': 102, 'name': 'First Coach', 'mobile': '+15550000001'},
            {'id': 103, 'name': 'Second Coach', 'mobile': '+15550000002'},
        ]
        self.db = MagicMock()
        self.db.execute.return_value.fetchone.return_value = self.admin
        self.db.execute.return_value.fetchall.return_value = self.coaches
        self.db_patch = patch.object(main, 'get_db', return_value=self.db)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.auth_patch = patch.object(main, 'get_auth_version', return_value=0)
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        with self.client.session_transaction() as session:
            session['_user_id'] = '101'
            session['_fresh'] = True
            session['auth_version'] = 0

    def test_exact_requested_template_and_personalization(self):
        expected = (
            "Morning [Name]! I've just posted my win of the week in Skool. Your turn 😊\n\n"
            "What's one moment from your group this week that made you smile? "
            "A PB, a kid who finally got it, a tough session they pushed through.\n\n"
            "One line is all I need 👉 skool.com/power2adapt-speed-school-8929\n\n"
            "Al"
        )
        self.assertEqual(SMS_TEMPLATES[0]['message'], expected)
        self.assertEqual(personalize_sms(expected, 'First Coach'), expected.replace('[Name]', 'First'))
        self.assertEqual(personalize_sms('Free text unchanged', 'First Coach'), 'Free text unchanged')

    def test_loading_alerts_provides_template_without_sending(self):
        with (
            patch.object(main, 'render_template', return_value='alerts') as render,
            patch.object(main, 'send_sms') as send,
        ):
            response = self.client.get('/alerts')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render.call_args.kwargs['sms_templates'], SMS_TEMPLATES)
        send.assert_not_called()

    def test_send_personalizes_each_recipient_and_logs_the_sent_body(self):
        message = SMS_TEMPLATES[0]['message']
        with patch.object(main, 'send_sms', return_value=True) as send:
            response = self.client.post('/alerts/send-custom', data={'message': message})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(send.call_count, 2)
        expected = [message.replace('[Name]', 'First'), message.replace('[Name]', 'Second')]
        self.assertEqual([call.args[-1] for call in send.call_args_list], expected)
        logs = [call.args[1][2] for call in self.db.execute.call_args_list
                if 'INSERT INTO sms_log' in call.args[0]]
        self.assertEqual(logs, expected)

    def test_selected_recipients_are_preserved(self):
        self.db.execute.return_value.fetchall.return_value = self.coaches[:1]
        with patch.object(main, 'send_sms', return_value=True) as send:
            self.client.post('/alerts/send-custom', data={
                'message': 'Morning [Name]!', 'coach_ids': ['102'],
            })
        send.assert_called_once()
        self.assertEqual(send.call_args.args[-1], 'Morning First!')
        selections = [call for call in self.db.execute.call_args_list
                      if 'WHERE id IN' in call.args[0]]
        self.assertEqual(selections[0].args[1], ['102'])

    def test_non_admin_cannot_send(self):
        self.admin['is_admin'] = 0
        with patch.object(main, 'send_sms') as send:
            response = self.client.post('/alerts/send-custom', data={'message': 'Morning [Name]!'})
        self.assertEqual(response.status_code, 302)
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
