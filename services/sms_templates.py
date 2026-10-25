SMS_TEMPLATES = (
    {
        'name': 'Skool — your turn to share a win',
        'message': (
            "Morning [Name]! I've just posted my win of the week in Skool. Your turn 😊\n\n"
            "What's one moment from your group this week that made you smile? "
            "A PB, a kid who finally got it, a tough session they pushed through.\n\n"
            "One line is all I need 👉 skool.com/power2adapt-speed-school-8929\n\n"
            "Al"
        ),
    },
)


def personalize_sms(message, coach_name):
    first_name = coach_name.split()[0] if coach_name and coach_name.split() else 'Coach'
    return message.replace('[Name]', first_name)
