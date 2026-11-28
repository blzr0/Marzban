import { Badge, HStack, IconButton, Text, Tooltip, chakra } from "@chakra-ui/react";
import { CheckIcon, ClipboardIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import { FC, useState } from "react";
import CopyToClipboard from "react-copy-to-clipboard";
import { useTranslation } from "react-i18next";
import { SubscriptionLogStatus } from "types/User";

const iconProps = {
  baseStyle: {
    w: 3.5,
    h: 3.5,
  },
};
const CopyIcon = chakra(ClipboardIcon, iconProps);
const CopiedIcon = chakra(CheckIcon, iconProps);

// long values (hwid, user agent, path) are cut to one line; hover shows the
// full text and the button copies it, so wide tables don't spread out
export const TruncatedCell: FC<{
  value: string | null | undefined;
  maxW?: string;
  copyable?: boolean;
}> = ({ value, maxW = "160px", copyable = false }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  if (!value) return <Text color="gray.500">—</Text>;
  return (
    <HStack spacing={1} maxW={maxW}>
      <Tooltip label={value} placement="top" openDelay={300}>
        <Text isTruncated>{value}</Text>
      </Tooltip>
      {copyable && (
        <CopyToClipboard
          text={value}
          onCopy={() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1000);
          }}
        >
          <IconButton
            aria-label={t("subscriptionLogs.copy")}
            size="xs"
            variant="ghost"
            minW="auto"
            h="auto"
            p={0.5}
          >
            {copied ? <CopiedIcon /> : <CopyIcon />}
          </IconButton>
        </CopyToClipboard>
      )}
    </HStack>
  );
};

const statusColors: Record<SubscriptionLogStatus, string> = {
  ok: "green",
  expired: "orange",
  revoked: "gray",
  hwid_limit_exceeded: "red",
  hwid_missing: "red",
};

export const LogStatusBadge: FC<{ status: SubscriptionLogStatus }> = ({
  status,
}) => {
  const { t } = useTranslation();
  return (
    <Badge colorScheme={statusColors[status] || "gray"} fontSize="2xs" whiteSpace="nowrap">
      {t(`subscriptionLogs.status.${status}`)}
    </Badge>
  );
};

export const deviceLine = (d: {
  device_model: string | null;
  device_os: string | null;
  os_version: string | null;
}): string =>
  [d.device_model, [d.device_os, d.os_version].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(" • ");

export const formatLogTime = (value: string): string =>
  dayjs.utc(value).local().format("DD.MM.YYYY HH:mm:ss");
