import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from services.scheduler import _send_skool_reminders


class SkoolReminderTests(unittest.TestCase):
    def test_weekly_wins_copy_is_personalized_and_delivery_is_logged(self):
        app = Flask(__name__)
        app.config.update(
            TWILIO_ACCOUNT_SID='test-account',
            TWILIO_AUTH_TOKEN='test-token',
            TWILIO_FROM_NUMBER='+15550000000',
        )
        coaches = [
            {'id': 101, 'name': 'First Coach', 'mobile': '+15550000001'},
            {'id': 102, 'name': 'Second Coach', 'mobile': '+15550000002'},
        ]
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = coaches
        with (
            patch('database.get_db', return_value=db),
            patch('services.twilio_service.send_sms', side_effect=[True, False]) as send,
        ):
            _send_skool_reminders(app)

        expected_body = (
            'Hey {name} 👋 Weekly wins are up in Skool!\n\n'
            'Drop one athlete moment from your sessions this week. One line is plenty. '
            'Something like "one of my Emerging Athletes finally nailed his arm drive in the 30m sprints."\n\n'
            "Got a photo of the drill or setup? Even better (no faces unless the family's said yes).\n\n"
            'Takes 2 mins 👉 skool.com/power2adapt-speed-school-8929\n\n'
            'Cheers, Al'
        )
        self.assertEqual(send.call_count, 2)
        for call, coach in zip(send.call_args_list, coaches):
            self.assertEqual(call.args, (
                'test-account', 'test-token', '+15550000000',
                coach['mobile'], expected_body.format(name=coach['name'].split()[0]),
            ))
        query = db.execute.call_args_list[0].args[0]
        self.assertIn('is_active = 1 AND mobile IS NOT NULL', query)
        log_calls = db.execute.call_args_list[1:]
        self.assertEqual([call.args[1][-2:] for call in log_calls], [
            ('skool_reminder', 'sent'), ('skool_reminder', 'failed'),
        ])
        db.commit.assert_called_once_with()
        db.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
