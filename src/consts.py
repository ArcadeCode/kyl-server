from datetime import timedelta

# Size limitations for various entities in the application
#
# Each char is stored in utf-8, so each ASCII char is 1 byte. The size limitation is in bytes.
# A card can take up to 8 kB
# A deck can take up to 200*8 kB = 1600 kB
# A user can have up to 100*1600 kB = 160 000 kB (160 MB)
MAX_DECK_BY_USER = 100
MAX_CARD_BY_DECK = 200
MAX_CARD_QUESTION_LENGTH = 4000
MAX_CARD_ANSWER_LENGTH = 4000

# Account rules
EMAIL_MAX_LENGTH = 254
NAME_MAX_LENGTH = 100

# Password security rules
#
# The password is sent in plain text over HTTPS and hashed server-side with
# bcrypt. bcrypt only reads the first 72 bytes of its input (and the bcrypt
# library raises an error beyond that), hence PASSWORD_MAX_LENGTH. The regex
# only allows ASCII characters, so 1 character == 1 byte.
PASSWORD_MIN_LENGTH = 5
PASSWORD_MAX_LENGTH = 72
# Keep the {min,max} bounds below in sync with the two constants above.
PASSWORD_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{5,72}$"

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

# Token security rules
# Fixed lifetime, no refresh: when the token expires, the user logs in again.
TOKEN_LIFESPAN = timedelta(days=30)
