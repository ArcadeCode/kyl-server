# Size limitations for various entities in the application
#
# Each char is store in utf-8, so each char is 1 byte. The size limitation is in bytes.
# A card can take up to 8 kB
# A deck can take up to 200*8 kB = 1600 kB
# A user can have up to 100*1600 kB = 160 000 kB (20 Ko)
MAX_DECK_BY_USER = 100
MAX_CARD_BY_DECK = 200
MAX_CARD_QUESTION_LENGTH = 4000
MAX_CARD_ANSWER_LENGTH = 4000

# Password security rules
#
# No PASSWORD_MAX_LENGTH because the hashing of the password
# is directly done client-side. It will take workload only
# on the client computer not the server.
# However, we have a BLAKE hash function and can check what
# the client send.
PASSWORD_MIN_LENGTH = 5
HASH_SIZE = 256  # bits
PASSWORD_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{5,}$"

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

# Token security rules
TOKEN_LIFESPAN = 3600 * 24 * 30  # 1 Month available token.
RESPONSE_CALLBACK_URL = "http://localhost:442/callback/"
