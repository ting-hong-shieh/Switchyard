// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

//! Local syntax validation for configured upstream base URLs.

use std::fs;
use std::path::Path;

use http::Uri;
use switchyard_server::{ServerError, ServerResult};

/// Reject malformed upstream URLs before dry-run succeeds or the server binds.
pub(super) fn validate_client_base_urls(path: &Path) -> ServerResult<()> {
    let source = fs::read_to_string(path).map_err(|error| {
        ServerError::new(format!(
            "failed to read server config {}: {error}",
            path.display()
        ))
    })?;
    let value: toml::Value = toml::from_str(&source).map_err(|error| {
        ServerError::new(format!(
            "invalid server config {}: failed to parse TOML: {error}",
            path.display()
        ))
    })?;
    let Some(clients) = value.get("llm_clients").and_then(toml::Value::as_table) else {
        return Ok(());
    };

    for (client_name, client) in clients {
        let Some(base_url) = client.get("base_url").and_then(toml::Value::as_str) else {
            continue;
        };
        validate_base_url(client_name, base_url).map_err(|message| {
            ServerError::new(format!("invalid server config {}: {message}", path.display()))
        })?;
    }
    Ok(())
}

fn validate_base_url(client_name: &str, base_url: &str) -> Result<(), String> {
    let uri = base_url.parse::<Uri>().map_err(|error| {
        format!(
            "llm client {client_name} base_url must be an absolute HTTP(S) URL: {error}"
        )
    })?;
    if !matches!(uri.scheme_str(), Some("http" | "https")) || uri.authority().is_none() {
        return Err(format!(
            "llm client {client_name} base_url must be an absolute HTTP(S) URL"
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_or_relative_urls() {
        assert!(validate_base_url("invalid", "not a url").is_err());
        assert!(validate_base_url("relative", "/v1").is_err());
        assert!(validate_base_url("scheme", "ftp://example.test/v1").is_err());
    }

    #[test]
    fn accepts_absolute_http_and_https_urls() {
        assert!(validate_base_url("local", "http://127.0.0.1:8000/v1").is_ok());
        assert!(validate_base_url("hosted", "https://example.test/v1").is_ok());
    }
}
