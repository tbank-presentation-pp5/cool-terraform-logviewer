import { Button, Card, Flex, Input, message, Select } from "antd";
import { useEffect, useState } from "react";
import { PlusCircleOutlined } from "@ant-design/icons";

const RawLogViewer = () => {
  const [keys, setKeys] = useState([]);
  const [options, setOptions] = useState([]);
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState({});
  const [count, setCount] = useState(1);

  const filteredOptions = options.filter(
    (o) =>
      !Object.values(filter)
        .map((e) => e.key)
        .includes(o.value)
  );

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/v2/filter/keys");
      const data = await response.json();
      setKeys(data);
      setOptions(getOptions(data));
    } catch (error) {
      console.log(`Failed to load keys: ${error}`);
    }
  };

  const postData = async () => {
    try {
      const valid = Object.values(filter)
        .filter((e) => e.key && e.value)
        .map((item) => [item.key, item.value]);
      const validDict = Object.fromEntries(valid);

      console.log(validDict);
      const response = await fetch("http://localhost:8000/api/v2/filter", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(validDict),
      });
      const data = await response.json();
      setLogs(data);
    } catch (error) {
      console.log(`Failed to filter: ${error}`);
      message.error(`Failed to filter`);
    }
  };

  const getOptions = (keys) => {
    const options = [];
    keys.forEach((item) => options.push({ value: item, label: item }));
    return options;
  };

  return (
    <div style={{ margin: '20px'}}>
      <Card title={"Raw Terraform Log Viewer"}>
        <Flex vertical>
          <Flex vertical gap={20}>
            {Array(count)
              .fill(0)
              .map((_, i) => (
                <Flex gap={20} key={i}>
                  <Select
                    value={filter[i]?.key}
                    onChange={(val) => {
                      setFilter((prev) => ({
                        ...prev,
                        [i]: { ...prev[i], key: val },
                      }));
                    }}
                    options={filteredOptions}
                    placeholder={"key"}
                    style={{ width: "100%", maxWidth: "350px" }}
                  />
                  <Input
                    value={filter[i]?.value}
                    onChange={(e) =>
                      setFilter((prev) => ({
                        ...prev,
                        [i]: { ...prev[i], value: e.target.value },
                      }))
                    }
                    placeholder={"value"}
                    style={{ width: "100%", maxWidth: "500px" }}
                  />
                </Flex>
              ))}

            <Flex justify={"space-between"} style={{ maxWidth: 870 }}>
              <Button
                icon={<PlusCircleOutlined />}
                onClick={() => setCount((p) => ++p)}
              >
                Добавить
              </Button>
              <Button type={"primary"} onClick={postData}>
                Применить
              </Button>
            </Flex>
          </Flex>

          {logs.map((log, i) => (
            <pre key={i}>{JSON.stringify(log, null, 2)}</pre>
          ))}
        </Flex>
      </Card>
    </div>
  );
};

export default RawLogViewer;
