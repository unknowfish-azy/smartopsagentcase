package com.smartops.security;

import org.junit.jupiter.api.Test;

import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OutboundUrlPolicyTest {

    @Test
    void publicIpv4LiteralIsAllowedWithoutDnsLookup() {
        assertTrue(OutboundUrlPolicy.isPublicHttpTarget(URI.create("http://8.8.8.8:8080/path")));
        assertTrue(OutboundUrlPolicy.isPublicHttpTarget(URI.create("https://1.1.1.1/")));
    }

    @Test
    void publicIpv6LiteralIsAllowed() {
        assertTrue(OutboundUrlPolicy.isPublicHttpTarget(URI.create("https://[2001:4860:4860::8888]/")));
    }

    @Test
    void loopbackAndPrivateIpv4AreBlocked() {
        for (String url : new String[]{
                "http://127.0.0.1:18080/",
                "http://127.1.2.3/",
                "http://10.0.0.1/",
                "http://172.16.0.1/",
                "http://192.168.1.1/",
                "http://169.254.169.254/latest/meta-data/",
                "http://100.64.0.1/",
                "http://198.18.0.1/",
                "http://0.0.0.0/",
                "http://224.0.0.1/",
                "http://255.255.255.255/"
        }) {
            assertEquals(OutboundUrlPolicy.Rule.NON_PUBLIC_ADDRESS,
                    OutboundUrlPolicy.inspect(URI.create(url)).rule(), url);
        }
    }

    @Test
    void ipv6SpecialRangesAreBlocked() {
        for (String url : new String[]{
                "http://[::1]/",
                "http://[::]/",
                "http://[fe80::1]/",
                "http://[fc00::1]/",
                "http://[2001:db8::1]/",
                "http://[::ffff:127.0.0.1]/",
                "http://[::ffff:192.168.0.1]/",
                "http://[64:ff9b::7f00:1]/"
        }) {
            assertEquals(OutboundUrlPolicy.Rule.NON_PUBLIC_ADDRESS,
                    OutboundUrlPolicy.inspect(URI.create(url)).rule(), url);
        }
    }

    @Test
    void trailingDotAndCaseDoNotBypassLocalhostRule() {
        assertEquals(OutboundUrlPolicy.Rule.LOCAL_HOST,
                OutboundUrlPolicy.inspect(URI.create("http://localhost.:18080/")).rule());
        assertEquals(OutboundUrlPolicy.Rule.LOCAL_HOST,
                OutboundUrlPolicy.inspect(URI.create("http://LOCALHOST/api")).rule());
        assertEquals("example.com", OutboundUrlPolicy.normalizeHost("ExAmPle.COM."));
    }

    @Test
    void nonHttpSchemesAndMissingHostAreBlocked() {
        assertEquals(OutboundUrlPolicy.Rule.SCHEME_NOT_ALLOWED,
                OutboundUrlPolicy.inspect(URI.create("ftp://8.8.8.8/file")).rule());
        assertEquals(OutboundUrlPolicy.Rule.SCHEME_NOT_ALLOWED,
                OutboundUrlPolicy.inspect(URI.create("file:///etc/passwd")).rule());
        assertEquals(OutboundUrlPolicy.Rule.HOST_MISSING,
                OutboundUrlPolicy.inspect(URI.create("http:/no-host")).rule());
        assertEquals(OutboundUrlPolicy.Rule.HOST_MISSING, OutboundUrlPolicy.inspect(null).rule());
    }

    @Test
    void assertPublicThrowsTypedRule() {
        OutboundUrlPolicy.BlockedUrlException failure = assertThrows(OutboundUrlPolicy.BlockedUrlException.class,
                () -> OutboundUrlPolicy.assertPublic(URI.create("http://[::1]:8080/")));
        assertEquals(OutboundUrlPolicy.Rule.NON_PUBLIC_ADDRESS, failure.rule());
    }

    @Test
    void literalAddressesAreClassifiedDirectly() throws Exception {
        assertFalse(OutboundUrlPolicy.isPublicAddress(java.net.InetAddress.getByName("127.0.0.1")));
        assertFalse(OutboundUrlPolicy.isPublicAddress(java.net.InetAddress.getByName("192.168.0.10")));
        assertTrue(OutboundUrlPolicy.isPublicAddress(java.net.InetAddress.getByName("8.8.4.4")));
    }
}
