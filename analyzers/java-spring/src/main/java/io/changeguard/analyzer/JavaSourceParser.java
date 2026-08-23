package io.changeguard.analyzer;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;

/**
 * Shared JavaParser configuration for ChangeGuard's semantic analyzers.
 *
 * The analyzer is compiled for Java 17 and must be able to parse Java 17 source
 * constructs such as records. Keeping parser configuration in one place prevents
 * individual semantic extractors from silently using JavaParser's default language
 * level.
 */
final class JavaSourceParser {

    static {
        StaticJavaParser.getParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17);
    }

    private JavaSourceParser() {
    }

    static CompilationUnit parse(String source) {
        return StaticJavaParser.parse(source);
    }
}
