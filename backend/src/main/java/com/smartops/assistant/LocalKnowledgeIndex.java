package com.smartops.assistant;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class LocalKnowledgeIndex {
    private static final int MAX_FILES = 128;
    private static final int MAX_FILE_BYTES = 65_536;
    private static final int MAX_TOTAL_BYTES = 2_097_152;
    private static final int MAX_CHUNKS = 512;
    private static final int MAX_ENTRIES = 2_048;
    private static final int CHUNK_CHARS = 1_000;
    private static final Pattern TERMS = Pattern.compile("[a-z0-9][a-z0-9_-]{1,63}|[\\p{IsHan}]+");

    private final Path root;
    private final List<MiniAssistantEngine.Evidence> builtin;
    private volatile List<MiniAssistantEngine.Evidence> snapshot;

    LocalKnowledgeIndex(Path root) {
        this(root, false);
    }

    LocalKnowledgeIndex(Path root, boolean includeBuiltin) {
        this.root = root.toAbsolutePath().normalize();
        this.builtin = includeBuiltin ? BuiltinKnowledgeCatalog.load() : List.of();
    }

    List<MiniAssistantEngine.Evidence> search(String query) {
        Set<String> terms = terms(query);
        if (terms.isEmpty()) {
            return List.of();
        }
        List<Ranked> matches = new ArrayList<>();
        List<MiniAssistantEngine.Evidence> candidates = new ArrayList<>(entries());
        candidates.addAll(builtin);
        for (MiniAssistantEngine.Evidence evidence : candidates) {
            String title = evidence.title().toLowerCase(Locale.ROOT);
            String text = evidence.snippet().toLowerCase(Locale.ROOT);
            int score = 0;
            for (String term : terms) {
                if (title.contains(term)) {
                    score += 3;
                }
                if (text.contains(term)) {
                    score++;
                }
            }
            if (score > 0) {
                matches.add(new Ranked(evidence, score));
            }
        }
        return matches.stream().sorted(Comparator.comparingInt(Ranked::score).reversed()
                        .thenComparing(match -> match.evidence().source())
                        .thenComparing(match -> match.evidence().id()))
                .limit(3).map(Ranked::evidence).toList();
    }

    private synchronized List<MiniAssistantEngine.Evidence> entries() {
        if (snapshot != null) {
            return snapshot;
        }
        List<MiniAssistantEngine.Evidence> result = new ArrayList<>();
        try {
            if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS) || !safePath(root)) {
                snapshot = List.of();
                return snapshot;
            }
            Budget budget = new Budget();
            read(root.resolve("smartopsagent_brain.md"), budget, result);
            for (String folder : List.of("assistant", "cloud_ops", "linux")) {
                Path directory = root.resolve(folder);
                if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS) || !safePath(directory)) {
                    continue;
                }
                int depth = "linux".equals(folder) ? 12 : 1;
                Files.walkFileTree(directory, EnumSet.noneOf(java.nio.file.FileVisitOption.class), depth,
                        new SimpleFileVisitor<>() {
                            @Override
                            public FileVisitResult preVisitDirectory(Path path, BasicFileAttributes attributes) {
                                if (++budget.entries > MAX_ENTRIES || budget.full(result)) {
                                    return FileVisitResult.TERMINATE;
                                }
                                return safePath(path) ? FileVisitResult.CONTINUE : FileVisitResult.SKIP_SUBTREE;
                            }

                            @Override
                            public FileVisitResult visitFile(Path path, BasicFileAttributes attributes) {
                                if (++budget.entries > MAX_ENTRIES || budget.full(result)) {
                                    return FileVisitResult.TERMINATE;
                                }
                                if (attributes.isRegularFile() && path.getFileName().toString().endsWith(".md")) {
                                    read(path, budget, result);
                                }
                                return FileVisitResult.CONTINUE;
                            }

                            @Override
                            public FileVisitResult visitFileFailed(Path path, IOException failure) {
                                return ++budget.entries > MAX_ENTRIES
                                        ? FileVisitResult.TERMINATE : FileVisitResult.CONTINUE;
                            }

                            @Override
                            public FileVisitResult postVisitDirectory(Path path, IOException failure) {
                                return FileVisitResult.CONTINUE;
                            }
                        });
                if (budget.full(result) || budget.entries >= MAX_ENTRIES) {
                    break;
                }
            }
        } catch (IOException | SecurityException failure) {
            snapshot = List.copyOf(result);
            return snapshot;
        }
        snapshot = List.copyOf(result);
        return snapshot;
    }

    private boolean safePath(Path path) {
        try {
            Path absolute = path.toAbsolutePath().normalize();
            if (!absolute.startsWith(root) || Files.isSymbolicLink(root)) {
                return false;
            }
            Path current = root;
            for (Path segment : root.relativize(absolute)) {
                current = current.resolve(segment);
                if (Files.isSymbolicLink(current)) {
                    return false;
                }
            }
            return true;
        } catch (SecurityException failure) {
            return false;
        }
    }

    private void read(Path file, Budget budget, List<MiniAssistantEngine.Evidence> result) {
        if (budget.full(result) || !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || !safePath(file)) {
            return;
        }
        try {
            String relative = root.relativize(file).toString().replace('\\', '/');
            if (relative.length() > 240 || Files.size(file) > MAX_FILE_BYTES) {
                return;
            }
            byte[] bytes;
            try (InputStream input = Files.newInputStream(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
                bytes = input.readNBytes(MAX_FILE_BYTES + 1);
            }
            if (bytes.length > MAX_FILE_BYTES || budget.bytes + bytes.length > MAX_TOTAL_BYTES || !safePath(file)) {
                return;
            }
            budget.files++;
            budget.bytes += bytes.length;
            String text = clean(new String(bytes, StandardCharsets.UTF_8));
            String title = file.getFileName().toString();
            for (String line : text.split("\\R", 32)) {
                if (line.startsWith("#")) {
                    title = line.replaceFirst("^#+\\s*", "").strip();
                    break;
                }
            }
            title = title.substring(0, Math.min(120, title.length()));
            String source = "knowledge/" + relative;
            for (int offset = 0, count = 0; offset < text.length() && count < 16 && result.size() < MAX_CHUNKS;
                    offset += CHUNK_CHARS - 100, count++) {
                int end = Math.min(text.length(), offset + CHUNK_CHARS);
                if (end < text.length() && Character.isHighSurrogate(text.charAt(end - 1))) {
                    end--;
                }
                String snippet = text.substring(offset, end).strip();
                if (!snippet.isEmpty()) {
                    String id = UUID.nameUUIDFromBytes((source + ":" + offset).getBytes(StandardCharsets.UTF_8)).toString();
                    result.add(new MiniAssistantEngine.Evidence(id, title, source, snippet));
                }
                if (end == text.length()) {
                    break;
                }
            }
        } catch (IOException | SecurityException failure) {
            return;
        }
    }

    private static String clean(String text) {
        StringBuilder result = new StringBuilder(text.length());
        for (int index = 0; index < text.length(); index++) {
            char character = text.charAt(index);
            result.append(Character.isISOControl(character) && character != '\n' && character != '\t' ? ' ' : character);
        }
        return result.toString();
    }

    private static Set<String> terms(String query) {
        Set<String> result = new LinkedHashSet<>();
        Matcher matcher = TERMS.matcher(query.toLowerCase(Locale.ROOT));
        while (matcher.find() && result.size() < 96) {
            String token = matcher.group();
            if (Character.UnicodeScript.of(token.codePointAt(0)) == Character.UnicodeScript.HAN) {
                int[] characters = token.codePoints().limit(128).toArray();
                if (characters.length == 1) {
                    result.add(token);
                }
                for (int index = 0; index + 1 < characters.length && result.size() < 96; index++) {
                    result.add(new String(characters, index, 2));
                }
            } else {
                result.add(token);
            }
        }
        return result;
    }

    private record Ranked(MiniAssistantEngine.Evidence evidence, int score) {}

    private static final class Budget {
        private int files;
        private int bytes;
        private int entries;

        private boolean full(List<MiniAssistantEngine.Evidence> chunks) {
            return files >= MAX_FILES || bytes >= MAX_TOTAL_BYTES || chunks.size() >= MAX_CHUNKS;
        }
    }
}
