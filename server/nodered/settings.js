// Node-RED settings for the book server. docker-compose.yml mounts this as /data/settings.js.
// The editor login is admin / NODERED_ADMIN_PASSWORD from .env (setup.sh makes it).
// Change this file, then: docker compose restart nodered
//
// Everything else Node-RED keeps lives in the nodered-data volume: flows, installed nodes, and
// the key that encrypts saved node credentials (.config.runtime.json). Back the volume up.
const path = require("path");

function adminAuth() {
    const password = process.env.NODERED_ADMIN_PASSWORD;
    if (!password) return undefined;         // no password set: no login (not on a shared network!)
    // bcryptjs comes with Node-RED; look for it from Node-RED's folder, not from /data
    const where = [path.dirname(require.main.filename)].concat(require.main.paths || []);
    const bcrypt = require(require.resolve("bcryptjs", { paths: where }));
    return {
        type: "credentials",
        users: [{ username: "admin", password: bcrypt.hashSync(password, 8), permissions: "*" }],
    };
}

module.exports = {
    uiPort: process.env.PORT || 1880,
    flowFile: "flows.json",
    flowFilePretty: true,                    // readable diffs if you keep flows in git
    adminAuth: adminAuth(),

    // context.set/get survive a restart (kept in /data/context)
    contextStorage: {
        default: { module: "localfilesystem" },
        memory: { module: "memory" },
    },

    functionExternalModules: true,           // a Function node may require() npm modules
    exportGlobalContextKeys: false,
    diagnostics: { enabled: false },
    logging: { console: { level: "info", metrics: false, audit: false } },
    editorTheme: { projects: { enabled: false } },
};
