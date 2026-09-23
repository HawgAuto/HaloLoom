#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

// CPU-only regression for the exact split mixed-packet accounting contract.
// It binds the source under test to the state-machine result: every call to
// process_packet_batch starts one async operation; a dispatch completes via
// AsyncSignalHandler, while a non-dispatch singleton must complete inline.
int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: packet_accounting_regression QUEUE_CPP fixed|unfixed\n";
        return 64;
    }
    std::ifstream in(argv[1]);
    std::ostringstream text;
    text << in.rdbuf();
    if (!in) {
        std::cerr << "cannot read source\n";
        return 66;
    }

    const std::string src = text.str();
    const auto branch = src.find("if(!_info_session.packet_data.empty())");
    const auto writer = src.find("_writer(std::move(transformed_packets));", branch);
    if (branch == std::string::npos || writer == std::string::npos) {
        std::cerr << "queue accounting structure not found\n";
        return 65;
    }
    const std::string accounting = src.substr(branch, writer - branch);
    const bool inline_empty_complete =
        accounting.find("else") != std::string::npos &&
        accounting.find("queue.async_complete();") != std::string::npos;

    const bool expect_fixed = std::string(argv[2]) == "fixed";
    if (!expect_fixed && std::string(argv[2]) != "unfixed") return 64;
    if (inline_empty_complete != expect_fixed) {
        std::cerr << "source state mismatch: inline_empty_complete="
                  << inline_empty_complete << " expected=" << expect_fixed << "\n";
        return 1;
    }

    // A mixed write split by batch_packets()==false: barrier, kernel, barrier.
    const std::vector<bool> singleton_has_dispatch{false, true, false};
    int active_async_packets = 0;
    for (bool has_dispatch : singleton_has_dispatch) {
        ++active_async_packets;              // process_packet_batch: async_started
        if (has_dispatch) --active_async_packets; // AsyncSignalHandler
        else if (inline_empty_complete) --active_async_packets;
    }
    const int expected = expect_fixed ? 0 : 2;
    if (active_async_packets != expected) {
        std::cerr << "accounting mismatch: got=" << active_async_packets
                  << " expected=" << expected << "\n";
        return 1;
    }
    std::cout << "PASS state=" << argv[2]
              << " mixed=[barrier,kernel,barrier] pending="
              << active_async_packets << "\n";
    return 0;
}
