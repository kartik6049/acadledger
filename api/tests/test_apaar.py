from app.apaar import ApaarStatus, MockApaarClient, verhoeff_check_digit, verhoeff_is_valid


def test_verhoeff_known_vector():
    # the worked example from Verhoeff's scheme: 236 -> check digit 3
    assert verhoeff_check_digit("236") == "3"
    assert verhoeff_is_valid("2363")
    assert not verhoeff_is_valid("2364")


def test_verhoeff_catches_adjacent_transposition():
    body = "12345678901"
    good = body + verhoeff_check_digit(body)
    swapped = good[:4] + good[5] + good[4] + good[6:]
    assert verhoeff_is_valid(good)
    assert not verhoeff_is_valid(swapped)


def test_mock_registry_knows_only_ids_with_a_valid_check_digit():
    body = "98765432109"
    registered = body + verhoeff_check_digit(body)
    unknown = body + str((int(registered[-1]) + 1) % 10)

    result = MockApaarClient().lookup_many([registered, unknown, registered])

    assert result[registered].status is ApaarStatus.FOUND
    assert result[unknown].status is ApaarStatus.NOT_FOUND
    assert len(result) == 2
