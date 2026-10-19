"""The names of the fields a document can produce.

Every country module uses these names, so a client reading documents from several countries sees the same
key for the same thing. A parser may only produce names from this list, and a spec may only require them
(tests and `DocumentSpec` enforce it). Need one that is missing? Add it here, with its meaning, in the same
change as the parser that uses it.

A document gives either `given_names` and `surname`, or `full_name` when the card prints the whole name as
one string. A name is never split by guesswork. Dates are ISO (`1990-01-12`).
"""

FIELD_NAMES: dict[str, str] = {
    "document_number": "Number of this document as printed: an ID card, passport or licence number",
    "national_id_number": "Holder's national ID number, for a document that is not the national ID itself",
    "given_names": "First names",
    "surname": "Main family name",
    "second_surname": "Second family name, on cards that print one",
    "full_name": "The whole name, when the card prints it as one string",
    "father_name": "Father's name",
    "sex": "M, F or X",
    "birth_date": "Date of birth",
    "issue_date": "Date of issue",
    "expiry_date": "Date of expiry",
    "nationality": "Nationality, ISO 3166-1 alpha-3",
    "issuing_country": "Issuing country, ISO 3166-1 alpha-3",
    "license_category": "Class of a driving licence, such as B1",
}
