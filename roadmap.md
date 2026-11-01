# Roadmap

- **v0.1.0** : Final touch
    - [ ] Make the Session historic infinite with compression of old entries.
    - [X] Setup the SMTP server for password reset.
- **v0.2.0** : FastAPI port
    - [ ] Switching the backend from Flask for FastAPI.
    - [ ] Add Pydantic to the backend.
    - [ ] Switch to JIT token.
    - [ ] Add API rating for each endpoint.
- **v0.3.0** : Gamification
    - [ ] Add flash card sorting system.
    - [ ] Add badges as achievements.
- **v1.0.0** : Better frontend
    - [ ] Choosing [Preact](https://preactjs.com/) or [Petite-vue](https://github.com/vuejs/petite-vue) as new framework.
- **v1.1.0** : OCR welcome and utils
    - [ ] Add Science formulas OCR for direct image to LaTex translation.
    - [ ] Add a "Share" button to decks for sharing a copy of the deck to an user by his email.
- **v1.2.0** : Bot !
    - [ ] Bot discord "kyl-bot" who remind user to continue working and allow a new backup method of the user data.

- **v2.0.0** : Future proof
    > The main goal of v2 is to make KYL more permissive, but it will requiert a big rework of the backend.
    - [ ] Allow importing Deck from other user, and auto-updating the imported Decks.
    - [ ] Allow multi-user owner for Deck.
    - [ ] Add Anki format handler.
    - [ ] Create other Cards formats.
        - Link columns
        - Multiple/single-choice question