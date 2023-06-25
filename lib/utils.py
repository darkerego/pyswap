import binascii
import json

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address


def json_file_load(file) -> any:
    """
    Load json file
    :param file: input
    :return: any
    """
    with open(file, 'r') as _f:
        return json.load(fp=_f)


def is_valid_evm_address(address_or_str: (ChecksumAddress, str)):
    try:
        to_checksum_address(address_or_str)
    except (ValueError, binascii.Error):
        return False
    return True
