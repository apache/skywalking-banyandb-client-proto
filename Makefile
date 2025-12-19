# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# BanyanDB Client Proto - Makefile

# Binaries
MVNW := ./mvnw

.PHONY: all check-versions generate compile clean sync-proto sync-proto-dry-run

all: compile

# Check versions
check-versions:
	@echo "Checking installed versions..."
	@echo "Required: JDK $(JDK_VERSION)"
	@echo ""
	@if command -v javac >/dev/null 2>&1; then \
		echo "javac version:"; \
		javac -version 2>&1 || $(JAVAC) -version 2>&1 || echo "  Not found"; \
	else \
		echo "javac: Not found"; \
	fi

# Generate Java code and compile using Maven
compile:
	@echo "Generating Java code and compiling using Maven..."
	@if [ ! -f pom.xml ]; then \
		echo "Error: pom.xml not found. Please ensure pom.xml exists in the project root."; \
		exit 1; \
	fi
	@if [ -f $(MVNW) ]; then \
		MVN_CMD=$(MVNW); \
	elif command -v mvn >/dev/null 2>&1; then \
		MVN_CMD=mvn; \
	else \
		echo "Error: Maven not found. Please run 'make install-mvnw' first or install Maven."; \
		exit 1; \
	fi; \
	echo "Using Maven: $$MVN_CMD"; \
	$$MVN_CMD clean compile || exit 1; \
	echo "Java code generated and compiled successfully."

# Clean generated files and Maven build artifacts
clean:
	@if [ -f $(MVNW) ] || command -v mvn >/dev/null 2>&1; then \
		if [ -f $(MVNW) ]; then \
			$(MVNW) clean 2>/dev/null || true; \
		elif command -v mvn >/dev/null 2>&1; then \
			mvn clean 2>/dev/null || true; \
		fi; \
	fi
	@echo "Clean completed."

# Sync proto files from Apache SkyWalking BanyanDB repository
sync-proto:
	@echo "Syncing proto files from Apache SkyWalking BanyanDB..."
	@python3 scripts/sync_proto.py

# Dry run: Preview proto file changes without writing
sync-proto-dry-run:
	@echo "Dry run: Previewing proto file changes..."
	@python3 scripts/sync_proto.py --dry-run

