from onix_fondeo.loader import load_all_configs, load_trades


def main():
    print("Starting Onix Fondeo Lab...")

    trades = load_trades()
    config = load_all_configs()

    print("\nTrades loaded successfully:")
    print(trades.head())

    print("\nEvaluation rules:")
    print(config["evaluation"])

    print("\nFunded rules:")
    print(config["funded"])

    print("\nSimulation settings:")
    print(config["simulation"])


if __name__ == "__main__":
    main()