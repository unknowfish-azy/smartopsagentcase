package com.smartops.security;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PinnedDnsTest {

    @AfterEach
    void clearPins() {
        // pin 登记是进程级静态表，测试间必须清干净，避免串扰。
        PinnedDns.clear("example.com");
        PinnedDns.clear("EXAMPLE.com.");
    }

    @Test
    void resolveReturnsExactlyThePinnedAddresses() throws Exception {
        InetAddress first = InetAddress.getByName("93.184.216.34");
        InetAddress second = InetAddress.getByName("93.184.216.35");
        PinnedDns.pin("example.com", List.of(first, second));

        assertArrayEquals(new InetAddress[]{first, second}, PinnedDns.resolve("example.com"));
    }

    @Test
    void unpinnedHostFailsClosed() {
        assertThrows(UnknownHostException.class, () -> PinnedDns.resolve("unpinned.example.org"));
    }

    @Test
    void pinIsCaseAndTrailingDotInsensitive() throws Exception {
        InetAddress address = InetAddress.getByName("93.184.216.34");
        PinnedDns.pin("Example.COM", List.of(address));

        assertArrayEquals(new InetAddress[]{address}, PinnedDns.resolve("example.com."));
        assertTrue(PinnedDns.isPinned("EXAMPLE.com"));
    }

    @Test
    void clearRemovesThePin() throws Exception {
        InetAddress address = InetAddress.getByName("93.184.216.34");
        PinnedDns.pin("example.com", List.of(address));
        assertTrue(PinnedDns.isPinned("example.com"));

        PinnedDns.clear("example.com");
        assertFalse(PinnedDns.isPinned("example.com"));
        assertThrows(UnknownHostException.class, () -> PinnedDns.resolve("example.com"));
    }

    @Test
    void blankOrEmptyPinsAreIgnored() {
        PinnedDns.pin(null, List.of());
        PinnedDns.pin("example.com", List.of());
        assertThrows(UnknownHostException.class, () -> PinnedDns.resolve("example.com"));
    }
}
