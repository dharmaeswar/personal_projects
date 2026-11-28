# syntax=docker/dockerfile:1
# Multi-stage build for the Spring Boot servicing API.
# Stage 1 compiles and tests; stage 2 ships only the JRE + jar.
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests=false test package -DskipTests=false

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/mortgage-servicing-fullstack-backend-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
