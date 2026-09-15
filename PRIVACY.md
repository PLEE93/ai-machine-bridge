# Privacy Policy

AI Machine Bridge is self-hosted software. The software itself does not operate a hosted data service, sell data, or send machine contents to its authors.

When you connect an AI client, reverse proxy, tunnel, browser target, or other third-party service, data may be transmitted to that service according to the service's own privacy policy and your configuration.

The bridge can access files, execute commands, control a browser, and run user-installed Python tools with the privileges of its service account. Requests and returned data are processed on the machine where you install the bridge unless your chosen network/client configuration sends them elsewhere.

The bearer credential grants powerful access to the installed machine. Keep it secret, restrict access to the bridge, and rotate the credential if it is exposed.

User-created files under the tools and memory directories remain on the installed machine unless a connected client intentionally reads or transmits them.

This generic policy describes the unmodified open-source software. If you publish a GPT, service, or product using the bridge, you are responsible for providing any additional privacy disclosures required for your deployment, jurisdiction, and third-party services.
