use base64::{engine::general_purpose::STANDARD, Engine as _};
use rcgen::{CertificateParams, KeyPair, PublicKeyData, SanType};
use rustls::pki_types::{CertificateDer, PrivateKeyDer};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::BufReader;
use std::io::Write;
use std::net::{IpAddr, Ipv4Addr};
use std::path::Path;
use std::sync::Arc;
use tauri::{AppHandle, Manager};

const IDENTITY_DIRECTORY: &str = "tls";
const PRIVATE_KEY_FILE: &str = "identity-key.pem";
const CERTIFICATE_FILE: &str = "identity-cert.pem";
static IDENTITY_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[derive(Debug, Clone)]
pub(crate) struct TlsIdentity {
    certificate_pem: String,
    private_key_pem: String,
    certificate_der: Vec<u8>,
    public_key_pin: String,
}

impl TlsIdentity {
    pub(crate) fn load_or_generate(
        app: &AppHandle,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        // Server startup and renderer info requests can race on first launch.
        let _guard = IDENTITY_LOCK
            .lock()
            .map_err(|_| "TLS identity lock poisoned")?;
        let directory = app.path().app_data_dir()?.join(IDENTITY_DIRECTORY);
        fs::create_dir_all(&directory)?;

        let key_path = directory.join(PRIVATE_KEY_FILE);
        let certificate_path = directory.join(CERTIFICATE_FILE);
        let (private_key_pem, certificate_pem) = match (
            fs::read_to_string(&key_path),
            fs::read_to_string(&certificate_path),
        ) {
            (Ok(key), Ok(certificate)) => (key, certificate),
            _ => {
                let (key, certificate) = generate_identity()?;
                write_private_file(&key_path, &key)?;
                write_private_file(&certificate_path, &certificate)?;
                (key, certificate)
            }
        };

        Self::from_pem(private_key_pem, certificate_pem)
    }

    fn from_pem(
        private_key_pem: String,
        certificate_pem: String,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let key_pair = KeyPair::from_pem(&private_key_pem)?;
        let certificate_der = first_certificate_der(&certificate_pem)?;
        let public_key_pin = spki_pin(key_pair.subject_public_key_info().as_ref());

        Ok(Self {
            certificate_pem,
            private_key_pem,
            certificate_der,
            public_key_pin,
        })
    }

    pub(crate) fn public_key_pin(&self) -> &str {
        &self.public_key_pin
    }

    pub(crate) fn server_config(
        &self,
    ) -> Result<rustls::ServerConfig, Box<dyn std::error::Error + Send + Sync>> {
        let certificates = certificate_chain(&self.certificate_pem)?;
        let private_key = private_key(&self.private_key_pem)?;

        Ok(rustls::ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(certificates, private_key)?)
    }

    pub(crate) fn client_config(
        &self,
        expected_pin: Option<&str>,
    ) -> Result<rustls::ClientConfig, Box<dyn std::error::Error + Send + Sync>> {
        if let Some(expected_pin) = expected_pin.filter(|pin| !pin.trim().is_empty()) {
            if expected_pin.trim() != self.public_key_pin {
                return Err(format!(
                    "WSS certificate pin does not match this desktop identity (expected {}, got {})",
                    expected_pin.trim(),
                    self.public_key_pin
                )
                .into());
            }
        }

        let mut roots = rustls::RootCertStore::empty();
        roots.add(CertificateDer::from(self.certificate_der.clone()))?;

        Ok(rustls::ClientConfig::builder()
            .with_root_certificates(Arc::new(roots))
            .with_no_client_auth())
    }
}

fn generate_identity() -> Result<(String, String), Box<dyn std::error::Error + Send + Sync>> {
    let key_pair = KeyPair::generate()?;
    let mut params = CertificateParams::new(vec!["localhost".to_string()])?;
    params
        .subject_alt_names
        .push(SanType::IpAddress(IpAddr::V4(Ipv4Addr::LOCALHOST)));
    let certificate = params.self_signed(&key_pair)?;

    Ok((key_pair.serialize_pem(), certificate.pem()))
}

fn first_certificate_der(
    certificate_pem: &str,
) -> Result<Vec<u8>, Box<dyn std::error::Error + Send + Sync>> {
    Ok(certificate_chain(certificate_pem)?
        .into_iter()
        .next()
        .ok_or("identity certificate PEM did not contain a certificate")?
        .as_ref()
        .to_vec())
}

fn certificate_chain(
    certificate_pem: &str,
) -> Result<Vec<CertificateDer<'static>>, Box<dyn std::error::Error + Send + Sync>> {
    Ok(
        rustls_pemfile::certs(&mut BufReader::new(certificate_pem.as_bytes()))
            .collect::<Result<Vec<_>, _>>()?,
    )
}

fn private_key(
    private_key_pem: &str,
) -> Result<PrivateKeyDer<'static>, Box<dyn std::error::Error + Send + Sync>> {
    rustls_pemfile::private_key(&mut BufReader::new(private_key_pem.as_bytes()))?
        .ok_or_else(|| "identity private-key PEM did not contain a private key".into())
}

fn write_private_file(path: &Path, contents: &str) -> std::io::Result<()> {
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);

    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    file.write_all(contents.as_bytes())
}

pub(crate) fn spki_pin(public_key: &[u8]) -> String {
    let digest = Sha256::digest(public_key);
    format!("sha256/{}", STANDARD.encode(digest))
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::{SinkExt, StreamExt};
    use rustls::pki_types::ServerName;
    use std::net::Ipv4Addr;
    use std::sync::Arc;
    use tokio::net::TcpListener;
    use tokio_rustls::{TlsAcceptor, TlsConnector};
    use tokio_tungstenite::tungstenite::{client::IntoClientRequest, Message};
    use tokio_tungstenite::{accept_async, client_async};

    #[test]
    fn public_key_pin_uses_the_standard_sha256_prefix() {
        let pin = super::spki_pin(&[0, 1, 2, 3]);

        assert!(pin.starts_with("sha256/"));
        assert_ne!(pin, "sha256/AAECAw==");
    }

    #[test]
    fn identical_public_keys_have_identical_pins() {
        assert_eq!(super::spki_pin(&[10, 20]), super::spki_pin(&[10, 20]));
    }

    #[test]
    fn different_public_keys_have_different_pins() {
        assert_ne!(super::spki_pin(&[10, 20]), super::spki_pin(&[10, 21]));
    }

    #[test]
    fn desktop_client_rejects_the_wrong_identity_pin() {
        let (key, cert) = generate_identity().unwrap();
        let identity = TlsIdentity::from_pem(key, cert).unwrap();
        assert!(identity
            .client_config(Some("sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="))
            .is_err());
    }

    #[cfg(unix)]
    #[test]
    fn identity_file_is_private_when_created_and_rewritten() {
        use std::os::unix::fs::PermissionsExt;
        let path =
            std::env::temp_dir().join(format!("blinky-key-permissions-{}", std::process::id()));
        write_private_file(&path, "test-only-key").unwrap();
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        write_private_file(&path, "replacement-test-key").unwrap();
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        fs::remove_file(path).unwrap();
    }

    #[tokio::test]
    async fn pinned_wss_round_trip_works() {
        let (private_key_pem, certificate_pem) = generate_identity().expect("identity");
        let identity =
            TlsIdentity::from_pem(private_key_pem, certificate_pem).expect("parse identity");
        let pin = identity.public_key_pin().to_string();
        let acceptor =
            TlsAcceptor::from(Arc::new(identity.server_config().expect("server config")));
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))
            .await
            .expect("bind test listener");
        let address = listener.local_addr().expect("listener address");

        let server = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept TCP");
            let tls_stream = acceptor.accept(stream).await.expect("accept TLS");
            let mut websocket = accept_async(tls_stream).await.expect("accept WebSocket");
            assert_eq!(
                websocket
                    .next()
                    .await
                    .expect("client message")
                    .expect("message"),
                Message::Text("ping".into())
            );
            websocket
                .send(Message::Text("pong".into()))
                .await
                .expect("send response");
        });

        let client_config = identity.client_config(Some(&pin)).expect("client config");
        let connector = TlsConnector::from(Arc::new(client_config));
        let tcp_stream = tokio::net::TcpStream::connect(address)
            .await
            .expect("connect TCP");
        let server_name = ServerName::try_from("127.0.0.1".to_string()).expect("server name");
        let tls_stream = connector
            .connect(server_name, tcp_stream)
            .await
            .expect("connect TLS");
        let request = format!("wss://127.0.0.1:{}/", address.port())
            .into_client_request()
            .expect("client request");
        let (mut websocket, _) = client_async(request, tls_stream)
            .await
            .expect("connect WebSocket");

        websocket
            .send(Message::Text("ping".into()))
            .await
            .expect("send request");
        assert_eq!(
            websocket
                .next()
                .await
                .expect("server response")
                .expect("message"),
            Message::Text("pong".into())
        );
        websocket.close(None).await.expect("close WebSocket");
        server.await.expect("server task");
    }
}
