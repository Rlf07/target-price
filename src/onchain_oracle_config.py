"""On-chain oracle contract configuration for bond price feeds."""

ONCHAIN_ORACLE_CONTRACTS: dict[str, dict] = {
    "tesouro": {
        "chain": "polygon",
        "address": "0xc1DF935339989f398C59aF034fdfc13b2a84C4F2",
        "pair_native": "TESOURO/BRZ",
        "quote_asset": "brz",
        "triangulate_via_forex": "brl",  # BRZ ≈ BRL para FX
        "decimals": 8,
        "transmit_selector": "2831fff3",
    },
    "gilts": {
        "chain": "polygon",
        "address": "0x3821A301b2cd8eB27831C54De61a8465C1C29b46",
        "pair_native": "GILTS/GBP",
        "quote_asset": "gbp",
        "triangulate_via_forex": "gbp",
        "decimals": 8,
        "transmit_selector": "2831fff3",
    },
    "ktb": {
        "chain": "monad",
        "address": "0x0087a2b1b36DBB75963b8eD25DFB370Ec1604460",
        "pair_native": "KTB/USD",
        "quote_asset": "usd",
        "triangulate_via_forex": None,
        "decimals": 8,
        "transmit_selector": "2831fff3",
    },
}

# Chainlink AnswerUpdated(bytes32 indexed current, int256 answer, ...)
ANSWER_UPDATED_TOPIC = "0x0559884fd3a460db3073b7fc896cc77986f16e378084d791dcde54156afa0756"

CHAIN_ID_BY_NAME = {
    "polygon": 137,
    "monad": 10143,  # confirm with infra if needed
}
