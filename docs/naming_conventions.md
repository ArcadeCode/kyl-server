# Naming conventions for `models/` files

- Each ORM class is named using CamelCase, and the corresponding table name is the lowercase version of the class name. For example, the `Session` class corresponds to the `session` table in the database.
- No pluralization is used for table names. The table name is the singular form of the class name, even if it represents a collection of entities. So for example `Card` class corresponds to the `card` table, not `cards`.
- ORM class attributes are named using snake_case, which is the standard naming for PostgreSQL columns. For example, the `deck_id` attribute corresponds to the `deck_id` column in the database.