-- 背单词助手：数据库与最小权限应用账号
-- 用法（管理员账号执行）：mysql -u root -p < scripts/setup_mysql.sql
-- 务必先把下面的密码改成你自己的强密码，并同步写入 backend/.env 或
-- %APPDATA%\背单词助手\.env 的 DB_PASSWORD。

CREATE DATABASE IF NOT EXISTS vocab_assistant
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Windows 上 TCP(127.0.0.1) 与 localhost 可能匹配不同 host 条目，故各建一个
CREATE USER IF NOT EXISTS 'vocab_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
CREATE USER IF NOT EXISTS 'vocab_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON vocab_assistant.* TO 'vocab_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON vocab_assistant.* TO 'vocab_app'@'127.0.0.1';

FLUSH PRIVILEGES;
