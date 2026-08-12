<?php
/**
 * Simple Mistral.ai Conversations API Client with Partial Base64 Encoding
 */

// Configuration - REPLACE WITH YOUR ACTUAL API KEY
define('MISTRAL_API_KEY', 'your-mistral-api-key-here');
define('MISTRAL_API_URL', 'https://api.mistral.ai/v1/conversations');

/**
 * Send request to Mistral Conversations API with partially encoded content
 */
function sendToMistralAPI($message, $model = 'mistral-tiny', $encodeFromIndex = 10) {
    
    // Partially encode the message
    $encodedMessage = partiallyBase64Encode($message, $encodeFromIndex);
    
    // Build request payload
    $payload = [
        'model' => $model,
        'messages' => [
            [
                'role' => 'user',
                'content' => $encodedMessage['formatted'],
                'metadata' => [
                    'encoding_info' => [
                        'original_length' => $encodedMessage['original_length'],
                        'encoded_length' => $encodedMessage['encoded_length'],
                        'encode_start_index' => $encodeFromIndex,
                        'encoding_type' => 'partial_base64'
                    ]
                ]
            ]
        ],
        'temperature' => 0.7,
        'max_tokens' => 150,
        'top_p' => 1.0,
    ];
    
    // Headers
    $headers = [
        'Content-Type: application/json',
        'Accept: application/json',
        'Authorization: Bearer ' . MISTRAL_API_KEY,
    ];
    
    // Initialize cURL
    $ch = curl_init(MISTRAL_API_URL);
    
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 30,
    ]);
    
    // Execute request
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    return [
        'success' => $error === '',
        'http_code' => $httpCode,
        'response' => $response,
        'error' => $error,
        'request_payload' => $payload,
        'encoded_message' => $encodedMessage
    ];
}

/**
 * Partially base64 encode a string from a specific index
 */
function partiallyBase64Encode($text, $startIndex = 0) {
    
    if ($startIndex <= 0) {
        // Encode entire string
        return [
            'original' => $text,
            'formatted' => '[BASE64:' . base64_encode($text) . ']',
            'original_length' => strlen($text),
            'encoded_length' => strlen(base64_encode($text))
        ];
    }
    
    if ($startIndex >= strlen($text)) {
        // No encoding needed
        return [
            'original' => $text,
            'formatted' => $text,
            'original_length' => strlen($text),
            'encoded_length' => 0
        ];
    }
    
    // Split and encode from startIndex
    $firstPart = substr($text, 0, $startIndex);
    $secondPart = substr($text, $startIndex);
    $encodedPart = base64_encode($secondPart);
    
    return [
        'original' => $text,
        'formatted' => $firstPart . '[BASE64:' . $encodedPart . ']',
        'original_length' => strlen($text),
        'encoded_length' => strlen($encodedPart)
    ];
}

/**
 * Decode a partially encoded message
 */
function decodePartiallyEncoded($formattedMessage) {
    
    if (strpos($formattedMessage, '[BASE64:') === false) {
        return $formattedMessage;
    }
    
    $parts = explode('[BASE64:', $formattedMessage, 2);
    $firstPart = $parts[0] ?? '';
    
    if (count($parts) < 2) {
        return $formattedMessage;
    }
    
    $encodedPart = rtrim($parts[1], ']');
    $decodedPart = base64_decode($encodedPart);
    
    return $firstPart . $decodedPart;
}

// Example Usage
echo "=== Mistral.ai Conversations API - Partial Base64 Encoding Demo ===\n\n";

// Sample message
$sampleMessage = "Hello Mistral AI! This is a test message to demonstrate partial base64 encoding in the API request.";

echo "Original Message:\n";
echo "$sampleMessage\n\n";

// Test partial encoding
$encoded = partiallyBase64Encode($sampleMessage, 18);
echo "Partially Encoded (from index 18):\n";
echo "{$encoded['formatted']}\n\n";

// Test decoding
$decoded = decodePartiallyEncoded($encoded['formatted']);
echo "Decoded Message:\n";
echo "$decoded\n\n";

// Verify decoding works
if ($decoded === $sampleMessage) {
    echo "✓ Decoding verification: SUCCESS\n\n";
} else {
    echo "✗ Decoding verification: FAILED\n\n";
}

// Send to API (commented out by default - uncomment to test)
/*
echo "Sending to Mistral API...\n";
$result = sendToMistralAPI($sampleMessage, 'mistral-tiny', 18);

if ($result['success']) {
    echo "API Request Successful!\n";
    echo "HTTP Code: {$result['http_code']}\n";
    echo "Response:\n";
    
    $responseData = json_decode($result['response'], true);
    if (json_last_error() === JSON_ERROR_NONE) {
        echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
    } else {
        echo $result['response'] . "\n";
    }
} else {
    echo "API Request Failed:\n";
    echo "Error: {$result['error']}\n";
    echo "HTTP Code: {$result['http_code']}\n";
}
*/

echo "\nNote: The actual API call is commented out. Uncomment the section above to test.\n";
echo "Remember to replace 'your-mistral-api-key-here' with your actual Mistral API key.\n";

// Display the exact request that would be sent
echo "\n=== Sample Request Payload ===\n";
$samplePayload = sendToMistralAPI($sampleMessage, 'mistral-tiny', 18);
echo json_encode($samplePayload['request_payload'], JSON_PRETTY_PRINT) . "\n";

?>