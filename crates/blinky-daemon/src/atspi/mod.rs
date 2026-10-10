use crate::protocol::models::UIElement;
use anyhow::{Context, Result};
use tracing::{debug, info};
use zbus::zvariant::Value;
use zbus::Connection;

pub struct AtspiBridge {
    a11y_conn: Option<Connection>,
}

impl AtspiBridge {
    pub async fn new() -> Self {
        let a11y_conn = Self::connect_a11y_bus().await.ok();
        Self { a11y_conn }
    }

    async fn connect_a11y_bus() -> Result<Connection> {
        let session = Connection::session().await?;
        let reply = session
            .call_method(
                Some("org.a11y.Bus"),
                "/org/a11y/bus",
                Some("org.a11y.Bus"),
                "GetAddress",
                &(),
            )
            .await
            .context("Failed to query org.a11y.Bus for accessibility address")?;

        let address: String = reply.body().deserialize()?;
        debug!("Discovered AT-SPI accessibility bus at: {}", address);

        let a11y_conn = zbus::connection::Builder::address(address.as_str())?
            .build()
            .await
            .context("Failed to connect to AT-SPI accessibility bus")?;

        Ok(a11y_conn)
    }

    pub async fn is_available(&self) -> bool {
        self.a11y_conn.is_some()
    }

    pub async fn get_elements(&self, max_elements: usize) -> Result<Vec<UIElement>> {
        let conn = match &self.a11y_conn {
            Some(c) => c,
            None => {
                debug!("AT-SPI bus not connected; returning empty elements");
                return Ok(Vec::new());
            }
        };

        // Query the root registry desktop object
        // Destination: org.a11y.atspi.Registry, Path: /org/a11y/atspi/accessible/root
        let root_children_reply = conn
            .call_method(
                Some("org.a11y.atspi.Registry"),
                "/org/a11y/atspi/accessible/root",
                Some("org.a11y.atspi.Accessible"),
                "GetChildren",
                &(),
            )
            .await;

        let root_children: Vec<(String, zbus::zvariant::OwnedObjectPath)> = match root_children_reply {
            Ok(reply) => reply.body().deserialize().unwrap_or_default(),
            Err(e) => {
                debug!("AT-SPI GetChildren on root failed: {}", e);
                return Ok(Vec::new());
            }
        };

        let mut elements = Vec::new();
        let mut elem_counter = 1;

        for (bus_name, path) in root_children {
            if elements.len() >= max_elements {
                break;
            }
            self.walk_node(
                conn,
                &bus_name,
                path.as_str(),
                0,
                max_elements,
                &mut elements,
                &mut elem_counter,
            )
            .await;
        }

        info!("AT-SPI bridge extracted {} accessible UI elements", elements.len());
        Ok(elements)
    }

    #[async_recursion::async_recursion]
    async fn walk_node(
        &self,
        conn: &Connection,
        bus_name: &str,
        path: &str,
        depth: usize,
        max_elements: usize,
        elements: &mut Vec<UIElement>,
        counter: &mut usize,
    ) {
        if depth > 5 || elements.len() >= max_elements {
            return;
        }

        // 1. Query Name
        let name_reply = conn
            .call_method(
                Some(bus_name),
                path,
                Some("org.freedesktop.DBus.Properties"),
                "Get",
                &("org.a11y.atspi.Accessible", "Name"),
            )
            .await;

        let name = if let Ok(reply) = name_reply {
            if let Ok(val) = reply.body().deserialize::<Value>() {
                match &val {
                    Value::Value(inner) => match &**inner {
                        Value::Str(s) => s.to_string(),
                        _ => String::new(),
                    },
                    Value::Str(s) => s.to_string(),
                    _ => String::new(),
                }
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        // 2. Query Role Name
        let role_reply = conn
            .call_method(
                Some(bus_name),
                path,
                Some("org.a11y.atspi.Accessible"),
                "GetRoleName",
                &(),
            )
            .await;

        let role_name: String = if let Ok(reply) = role_reply {
            reply.body().deserialize().unwrap_or_default()
        } else {
            "unknown".to_string()
        };

        // 3. Query Bounding Box Extents (coord_type = 0 DESKTOP_COORDS)
        let extents_reply = conn
            .call_method(
                Some(bus_name),
                path,
                Some("org.a11y.atspi.Component"),
                "GetExtents",
                &(0u32),
            )
            .await;

        if let Ok(reply) = extents_reply {
            if let Ok((x, y, w, h)) = reply.body().deserialize::<(i32, i32, i32, i32)>() {
                if w > 0 && h > 0 && (!name.is_empty() || role_name != "unknown") {
                    elements.push(UIElement {
                        ref_id: format!("@a{}", *counter),
                        text: name,
                        x,
                        y,
                        width: w as u32,
                        height: h as u32,
                        confidence: Some(1.0),
                        role: Some(role_name),
                    });
                    *counter += 1;
                }
            }
        }

        // 4. Recurse into children
        let children_reply = conn
            .call_method(
                Some(bus_name),
                path,
                Some("org.a11y.atspi.Accessible"),
                "GetChildren",
                &(),
            )
            .await;

        if let Ok(reply) = children_reply {
            if let Ok(children) = reply.body().deserialize::<Vec<(String, zbus::zvariant::OwnedObjectPath)>>() {
                for (child_bus, child_path) in children {
                    if elements.len() >= max_elements {
                        break;
                    }
                    let target_bus = if child_bus.is_empty() { bus_name } else { &child_bus };
                    self.walk_node(
                        conn,
                        target_bus,
                        child_path.as_str(),
                        depth + 1,
                        max_elements,
                        elements,
                        counter,
                    )
                    .await;
                }
            }
        }
    }
}
