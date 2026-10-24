package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.web.multipart.MultipartFile;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Set;

public final class ChatAttachmentValidator {
    private ChatAttachmentValidator() {}
    public static final long MB = 1024 * 1024;

    public static Validated validate(MultipartFile file) {
        String name = file.getOriginalFilename();
        if (name == null || name.isBlank() || name.length() > 160 || name.matches(".*[\\\\/\\p{Cntrl}].*")) fail("文件名无效");
        String extension = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
        boolean image = Set.of("png", "jpg", "jpeg").contains(extension);
        if (!image && !Set.of("txt", "log", "md").contains(extension)) fail("首批仅支持 PNG、JPEG、UTF-8 TXT、LOG、MD；其他格式尚未开放");
        long limit = (image ? 10 : 20) * MB;
        if (file.isEmpty() || file.getSize() > limit) fail("文件为空或超过大小限制");
        String type = image ? (extension.equals("png") ? "image/png" : "image/jpeg") : "text/plain";
        String declared = file.getContentType();
        if (declared != null && !declared.isBlank() && !declared.equals("application/octet-stream")
                && !declared.equals(type) && !(extension.equals("md") && declared.equals("text/markdown"))) fail("文件类型与扩展名不匹配");
        try {
            byte[] original;
            try (var stream = file.getInputStream()) { original = stream.readNBytes((int) limit + 1); }
            if (original.length == 0 || original.length > limit) fail("文件为空或超过大小限制");
            String hash = digest(name + "\n" + type + "\n" + digest(original));
            byte[] bytes = original;
            if (image) {
                boolean png = original.length >= 8 && original[0] == (byte) 137 && original[1] == 80 && original[2] == 78 && original[3] == 71
                        && original[4] == 13 && original[5] == 10 && original[6] == 26 && original[7] == 10;
                boolean jpeg = original.length >= 3 && original[0] == (byte) 255 && original[1] == (byte) 216 && original[2] == (byte) 255;
                if (!(extension.equals("png") ? png : jpeg)) fail("图片文件签名无效");
                try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(original))) {
                    var readers = ImageIO.getImageReaders(input);
                    if (!readers.hasNext()) fail("图片无法安全解码");
                    var reader = readers.next();
                    try {
                        reader.setInput(input, true, true);
                        long width = reader.getWidth(0), height = reader.getHeight(0);
                        if (width < 1 || height < 1 || width * height > 20_000_000L) fail("图片超过 2000 万像素限制");
                        var decoded = reader.read(0);
                        var output = new ByteArrayOutputStream();
                        if (!ImageIO.write(decoded, extension.equals("png") ? "png" : "jpg", output)) fail("图片无法重新编码");
                        bytes = output.toByteArray();
                        if (bytes.length > limit) fail("安全处理后的图片超过大小限制");
                    } finally { reader.dispose(); }
                }
            } else {
                String text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(original)).toString();
                if (text.codePoints().anyMatch(value -> Character.isISOControl(value) && value != 9 && value != 10 && value != 13)) fail("仅支持 UTF-8 文本，不支持二进制内容");
            }
            return new Validated(name, type, bytes, hash);
        } catch (BusinessException failure) { throw failure; }
        catch (Exception invalid) { throw new BusinessException(400, "文件损坏或编码不受支持，请使用 PNG、JPEG 或 UTF-8 文本"); }
    }

    public static String digest(String text) { return digest(text.getBytes(StandardCharsets.UTF_8)); }
    private static String digest(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static void fail(String message) { throw new BusinessException(400, message); }
    public record Validated(String name, String mediaType, byte[] bytes, String requestHash) {}
}
