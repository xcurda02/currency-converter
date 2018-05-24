#!/usr/bin/env python3

from flask import Flask, request, Response
from forex_python.converter import CurrencyRates, RatesNotAvailableError
from forex_python.bitcoin import BtcConverter
from requests.exceptions import ConnectionError
import sys
import argparse
import json
import os

app = Flask(__name__)


# Error messages
class ErrorMsg:
    no_connection = "ERROR: No connection to a currency server"
    rate_not_available = "ERROR: Currency rate not available"
    unknown_currency = "ERROR: Unknown currency"
    same_currency = "ERROR: Cannot convert into the same currency"
    float_arg_expected = "ERROR: Amount argument expected as float number"


# Exception defining an unknown currency error
class UnknownCurrencyError(Exception):
    pass


# Exception defining conversion of currency into the same currency
class SameCurrencyError(Exception):
    pass


# Method accepting GET /currency_converter requests
@app.route('/currency_converter')
def currency_converter_api():
    try:
        amount = float(request.args.get('amount'))
    except ValueError:              # Not a float number
        return Response(ErrorMsg.float_arg_expected, status=400)

    input_currency = request.args.get('input_currency')
    output_currency = request.args.get('output_currency')

    try:
        output = convert(amount, input_currency, output_currency)
    except ConnectionError:         # Error connecting to currency server
        return Response(ErrorMsg.no_connection, status=503)
    except RatesNotAvailableError:  # Rate not available for requested currencies
        return Response(ErrorMsg.rate_not_available, status=405)
    except UnknownCurrencyError:    # Unknown currency entered
        return Response(ErrorMsg.unknown_currency, status=400)
    except SameCurrencyError:       # Converting into same currency
        return Response(ErrorMsg.same_currency, status=400)

    return output


# Getting currency data from file
def get_currency_data():
    file_path = os.path.dirname(os.path.abspath(__file__))
    with open(file_path + '/symbols.json') as f:
        return json.loads(f.read())


# Determine if currency string is currency code
def is_currency_code(currency_string):
    currency_data = get_currency_data()

    for item in currency_data:
        if item['cc'] == currency_string:
            return True

    return False


# Returns currency code from currency symbol
# Currencies that share their symbol are selected based on alphabetical order,
# except USD which is selected no matter of its alphabetical order
# Currencies sharing one currency symbol:
# $	    ['AUD', 'CAD', 'MXN', 'USD']
# ¥	    ['CNY', 'JPY']
# kr	['ISK', 'NOK', 'SEK']
# R	    ['RUB', 'ZAR']
def get_currency_code(currency):
    if is_currency_code(currency):
        return currency

    # Hard coded selection of USD
    if currency == "$":
        return "USD"

    # Getting currency data from file
    currency_data = get_currency_data()

    # Finding symbol from parameter and returning given currency code
    for item in currency_data:
        if item['symbol'] == currency:
            return item['cc']

    return None


# Converts input currency and returns result in json
def convert(amount, input_currency, output_currency):
    input_currency_code = get_currency_code(input_currency)
    if input_currency_code is None:         # Input currency code was not found - unknown currency
        raise UnknownCurrencyError

    if output_currency is not None:
        output_currency_code = get_currency_code(output_currency)
        if output_currency_code is None:    # Output currency code was not found - unknown currency
            raise UnknownCurrencyError
        currency_data = [{'cc': output_currency_code}]
    else:
        # Getting currency data from file
        currency_data = get_currency_data()

    c = CurrencyRates()
    b = BtcConverter()
    output_currencies = dict()  # Dictionary to store converted amounts for each currency

    # Converting currency
    for item in currency_data:
        if item['cc'] == input_currency_code:       # Out currency == in currency
            if output_currency is None:
                continue
            else:
                raise SameCurrencyError

        try:
            if input_currency_code == "BTC":    # Bitcoin is input currency
                output_currencies[item['cc']] = round(b.convert_btc_to_cur(amount, item['cc']), 2)

            elif item['cc'] == "BTC":           # Bitcoin is output currency
                output_currencies[item['cc']] = round(b.convert_to_btc(amount, input_currency_code), 5)

            else:                               # Other currencies than bitcoin
                output_currencies[item['cc']] = round(c.convert(input_currency_code, item['cc'], amount), 2)

        except RatesNotAvailableError:
            if output_currency is None:  # Output currency not entered, currencies without available rates are skipped
                pass
            else:  # Output currency entered => not available currency rate yields error
                raise RatesNotAvailableError

    output_data = dict()
    output_data['input'] = {'amount': amount, 'currency': input_currency_code}
    output_data['output'] = output_currencies

    return json.dumps(output_data, indent='\t')


# CLI args parser
def handle_cli_args():
    parser = argparse.ArgumentParser(add_help=False, description='Currency converter')

    required_named = parser.add_argument_group('Required arguments')

    required_named.add_argument('--amount', action='store', dest='amount',
                                required='--help' not in sys.argv and '-h' not in sys.argv,
                                help='Amount', type=float)

    required_named.add_argument('--input_currency', action='store', dest='input_currency',
                                required='--help' not in sys.argv and '-h' not in sys.argv,
                                help='Input currency')

    parser.add_argument('--output_currency', action='store', dest='output_currency',
                        help='Output currency', default=None)

    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Print help')

    args = parser.parse_args()

    return args


def main():
    # CLI app
    if len(sys.argv) != 1:
        try:
            args = handle_cli_args()
        except SystemExit:
            if '--help' not in sys.argv and '-h' not in sys.argv:
                sys.exit(1)
            else:
                sys.exit(0)
        try:
            output = convert(args.amount, args.input_currency, args.output_currency)
        except ConnectionError:         # Error connecting to currency server
            sys.stderr.write(ErrorMsg.no_connection+'\n')
            sys.exit(2)
        except RatesNotAvailableError:  # Rate not available for requested currencies
            sys.stderr.write(ErrorMsg.rate_not_available+'\n')
            sys.exit(3)
        except UnknownCurrencyError:    # Unknown currency entered
            sys.stderr.write(ErrorMsg.unknown_currency+'\n')
            sys.exit(4)
        except SameCurrencyError:       # Converting into same currency
            sys.stderr.write(ErrorMsg.same_currency+'\n')
            sys.exit(5)

        print(output)

    # web API
    else:
        app.run()


if __name__ == "__main__":
    main()
