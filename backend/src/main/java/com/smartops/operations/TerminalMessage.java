package com.smartops.operations;

public record TerminalMessage(String type, String runtimeId, String data, Integer columns, Integer rows) {
    public static TerminalMessage input(String runtimeId, String data) { return new TerminalMessage("INPUT", runtimeId, data, null, null); }
}
