import {
  Badge,
  Box,
  Button,
  HStack,
  IconButton,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tooltip,
  Tr,
  chakra,
  useToast,
} from "@chakra-ui/react";
import { TrashIcon } from "@heroicons/react/24/outline";
import { FC, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetch } from "service/http";
import { UserHWID } from "types/User";
import { TruncatedCell, deviceLine, formatLogTime } from "./SubscriptionLogCells";

const DeleteIcon = chakra(TrashIcon, {
  baseStyle: {
    w: 4,
    h: 4,
  },
});

// devices bound to the user by the x-hwid header, with unbind/reset
export const UserHWIDs: FC<{ username: string; hwidLimit: number }> = ({
  username,
  hwidLimit,
}) => {
  const { t } = useTranslation();
  const toast = useToast();
  const [hwids, setHwids] = useState<UserHWID[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    fetch<{ hwids: UserHWID[] }>(`/user/${username}/hwids`)
      .then((data) => setHwids(data.hwids))
      .catch(() => setHwids([]))
      .finally(() => setLoading(false));
  };

  useEffect(load, [username]);

  const remove = (path: string) => {
    setBusy(true);
    fetch(path, { method: "DELETE" })
      .then(() => {
        toast({
          title: t("userHwids.removed"),
          status: "success",
          isClosable: true,
          position: "top",
          duration: 2000,
        });
        load();
      })
      .catch(() => {
        toast({
          title: t("userHwids.removeError"),
          status: "error",
          isClosable: true,
          position: "top",
          duration: 3000,
        });
      })
      .finally(() => setBusy(false));
  };

  const overLimit = hwidLimit > 0 && hwids.length >= hwidLimit;

  return (
    <Box w="full">
      <HStack justifyContent="space-between" mb={2}>
        <HStack>
          <Text fontWeight="semibold" fontSize="sm">
            {t("userHwids.title")}
          </Text>
          <Badge colorScheme={overLimit ? "red" : "primary"}>
            {hwids.length}/{hwidLimit > 0 ? hwidLimit : "∞"}
          </Badge>
          {loading && <Spinner size="xs" />}
        </HStack>
        {hwids.length > 0 && (
          <Button
            size="xs"
            variant="outline"
            colorScheme="red"
            isDisabled={busy}
            onClick={() => remove(`/user/${username}/hwids`)}
          >
            {t("userHwids.resetAll")}
          </Button>
        )}
      </HStack>
      {hwids.length === 0 ? (
        <Text fontSize="sm" color="gray.500">
          {t("userHwids.empty")}
        </Text>
      ) : (
        <Box overflowX="auto" borderWidth="1px" borderRadius="md">
          <Table size="sm" fontSize="xs">
            <Thead>
              <Tr>
                <Th>HWID</Th>
                <Th>{t("subscriptionLogs.device")}</Th>
                <Th>{t("subscriptionLogs.domain")}</Th>
                <Th>User-Agent</Th>
                <Th>IP</Th>
                <Th>{t("userHwids.lastSeen")}</Th>
                <Th />
              </Tr>
            </Thead>
            <Tbody>
              {hwids.map((d) => (
                <Tr key={d.id}>
                  <Td>
                    <TruncatedCell value={d.hwid} maxW="130px" copyable />
                  </Td>
                  <Td>
                    <TruncatedCell value={deviceLine(d)} maxW="140px" />
                  </Td>
                  <Td>
                    <TruncatedCell value={d.host} maxW="120px" />
                  </Td>
                  <Td>
                    <TruncatedCell value={d.user_agent} maxW="110px" copyable />
                  </Td>
                  <Td whiteSpace="nowrap">{d.ip || "—"}</Td>
                  <Td whiteSpace="nowrap">
                    <Tooltip
                      label={`${t("userHwids.firstSeen")}: ${formatLogTime(d.created_at)}`}
                    >
                      <Text>{formatLogTime(d.last_seen_at)}</Text>
                    </Tooltip>
                  </Td>
                  <Td>
                    <Tooltip label={t("userHwids.remove")}>
                      <IconButton
                        aria-label={t("userHwids.remove")}
                        size="xs"
                        variant="ghost"
                        isDisabled={busy}
                        onClick={() => remove(`/user/${username}/hwids/${d.id}`)}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}
    </Box>
  );
};
