import socket
import struct


def build_query(domain):
    """Build a raw DNS query packet for an A record lookup."""
    transaction_id = 0x1234
    flags = 0x0100                # standard query, recursion desired
    qdcount = 1
    ancount = 0
    nscount = 0
    arcount = 0

    header = struct.pack(">HHHHHH",
        transaction_id, flags, qdcount, ancount, nscount, arcount
    )

    # Encode domain: "google.com" -> \x06google\x03com\x00
    question = b""
    for part in domain.split("."):
        question += bytes([len(part)]) + part.encode()
    question += b"\x00"

    qtype = 1    # A record = IPv4
    qclass = 1   # IN = internet
    question += struct.pack(">HH", qtype, qclass)

    return header + question


def resolve(domain):
    """
    Resolve a domain to an IPv4 address using a raw DNS query to 8.8.8.8.
    Returns the first A record as a string, or None on failure.

    Added proper error handling for timeouts and exceptions.
    Correctly handles both compressed (0xC0) and uncompressed name
         pointers in answer records — the original code assumed all answers
         used a 2-byte compressed pointer, which broke on some DNS responses.
    """
    dns_server = "8.8.8.8"
    dns_port = 53

    query = build_query(domain)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        sock.sendto(query, (dns_server, dns_port))
        response, _ = sock.recvfrom(512)
        sock.close()
    except socket.timeout:
        print(f"[DNS] Timeout resolving: {domain}")
        return None
    except Exception as e:
        print(f"[DNS] Error resolving {domain}: {e}")
        return None

    # Unpack 12-byte header
    transaction_id, flags, qdcount, ancount, nscount, arcount = \
        struct.unpack(">HHHHHH", response[:12])

    # Skip question section
    offset = 12
    for _ in range(qdcount):
        while offset < len(response) and response[offset] != 0:
            offset += response[offset] + 1
        offset += 5  # null byte + qtype (2) + qclass (2)

    # Parse answer records
    ips = []
    for _ in range(ancount):
        if offset + 2 > len(response):
            break

        # DNS name compression: pointer starts with bits 11 (0xC0)
        if response[offset] & 0xC0 == 0xC0:
            offset += 2           # compressed pointer is always 2 bytes
        else:
            while offset < len(response) and response[offset] != 0:
                offset += response[offset] + 1
            offset += 1           # skip the null terminator

        if offset + 10 > len(response):
            break

        rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", response[offset:offset + 10])
        offset += 10

        if rtype == 1 and rdlength == 4:  # A record = 4-byte IPv4
            ip = ".".join(str(b) for b in response[offset:offset + 4])
            ips.append(ip)

        offset += rdlength

    return ips[0] if ips else None



if __name__ == "__main__":
    import sys
    domain = sys.argv[1] if len(sys.argv) > 1 else "google.com"
    ip = resolve(domain)
    if ip:
        print(f"{domain} -> {ip}")
    else:
        print(f"[DNS] Could not resolve: {domain}")